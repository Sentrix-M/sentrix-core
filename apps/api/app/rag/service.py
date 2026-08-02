"""RAG service — orchestrates the document ingestion pipeline.

Coordinates the loader → parser → chunker → repository pipeline for a
single upload. The service is intentionally stateless: it accepts an
``UploadFile``, processes it through the pipeline, and returns a
``DocumentUploadResponse``.

Usage::

    svc = RagService(repository=repo)
    result = await svc.ingest_pdf(upload_file)
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.rag.chunker import ChunkingConfig, TextChunker
from app.rag.loader import PdfLoader
from app.rag.parser import TextParser
from app.rag.repository import InMemoryDocumentRepository
from app.rag.retriever import SemanticRetriever
from app.rag.schemas import (
    Document,
    DocumentListResponse,
    DocumentUploadResponse,
    SearchResultItem,
)

logger = logging.getLogger(__name__)


class RagService:
    """Orchestrates the document ingestion pipeline.

    :param repository: The document/chunk repository.
    :param loader: PDF loader instance. Defaults to a fresh ``PdfLoader``.
    :param parser: Text parser instance. Defaults to a fresh ``TextParser``.
    :param chunker: Text chunker instance. Defaults to a fresh
        ``TextChunker``.
    :param chunking_config: Override chunking parameters. Defaults to
        :attr:`TextChunker.DEFAULT_CONFIG`.
    """

    def __init__(
        self,
        repository: InMemoryDocumentRepository,
        *,
        loader: PdfLoader | None = None,
        parser: TextParser | None = None,
        chunker: TextChunker | None = None,
        chunking_config: ChunkingConfig | None = None,
    ) -> None:
        self._repository = repository
        self._loader = loader or PdfLoader()
        self._parser = parser or TextParser()
        self._chunker = chunker or TextChunker()
        self._chunking_config = chunking_config or ChunkingConfig()
        self._retriever = SemanticRetriever()

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    async def ingest_pdf(
        self,
        content: bytes,
        *,
        filename: str,
    ) -> DocumentUploadResponse:
        """Ingest a PDF file: load -> parse -> chunk -> store -> index.

        :param content: Raw PDF bytes.
        :param filename: Original filename.
        :returns: Upload response with document metadata.
        :raises PdfLoadError: If the PDF cannot be read.
        """
        logger.info("Ingesting PDF '%s' (%d bytes).", filename, len(content))

        # 1. Load.
        pdf_doc = self._loader.load(content, filename=filename)

        # 2. Parse.
        parsed_doc = self._parser.parse(pdf_doc.pages, filename=filename)

        # 3. Create document record (before chunking so we have a UUID).
        import uuid  # noqa: PLC0415

        document_id = uuid.uuid4()
        document = Document(
            id=document_id,
            filename=filename,
            page_count=parsed_doc.page_count,
        )
        await self._repository.create_document(document)

        # 4. Chunk.
        chunks = self._chunker.chunk(
            parsed_doc,
            config=self._chunking_config,
            document_id=document_id,
        )

        # 5. Store chunks.
        stored_count = await self._repository.save_chunks(document_id, chunks)

        # 6. Update document with chunk count.
        updated = document.model_copy(update={"total_chunks": stored_count})
        # The repository uses frozen=True, so we replace the stored record.
        # In a production repo we'd have an update method; for in-memory
        # we just overwrite the frozen copy.
        self._repository._documents[document_id] = updated  # noqa: SLF001

        # 7. Auto-index chunks into the vector store for semantic search.
        chunk_dicts = [
            {
                "id": c.id,
                "document_id": c.document_id,
                "text": c.text,
                "filename": c.filename,
                "page_number": c.page_number,
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ]
        indexed = self._retriever.index_chunks(chunk_dicts)
        logger.info(
            "Indexed %d/%d chunks into vector store.", indexed, stored_count
        )

        logger.info(
            "Ingested '%s': %d pages -> %d chunks.",
            filename,
            parsed_doc.page_count,
            stored_count,
        )

        return DocumentUploadResponse(
            document_id=document_id,
            filename=filename,
            page_count=parsed_doc.page_count,
            total_chunks=stored_count,
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def list_documents(self) -> DocumentListResponse:
        """Return a list of all ingested documents."""
        docs = await self._repository.list_documents()
        return DocumentListResponse(documents=docs, total=len(docs))

    async def get_document_chunks(self, document_id: UUID) -> list:
        """Return all chunks for a document (for internal use)."""
        return await self._repository.get_chunks(document_id)

    async def search(self, query: str, *, top_k: int = 5) -> list[SearchResultItem]:
        """Semantic search over ingested document chunks.

        :param query: Natural-language search query.
        :param top_k: Number of results to return.
        :returns: List of :class:`SearchResultItem` with metadata.
        """
        results = self._retriever.search(query, top_k=top_k)
        return [
            SearchResultItem(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                text=r.text,
                filename=r.filename,
                page_number=r.page_number,
                chunk_index=r.chunk_index,
                score=r.score,
            )
            for r in results
        ]


__all__ = ["RagService"]
