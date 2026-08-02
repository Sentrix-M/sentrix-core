"""In-memory repository for RAG documents and chunks.

Provides thread-safe storage for the document ingestion pipeline. No
vector database, no persistence — just a dict-based store for development
and testing. The interface is designed so a future PostgreSQL/ChromaDB
implementation can be swapped in without changing the service layer.
"""

from __future__ import annotations

import threading
from uuid import UUID

from app.rag.schemas import Chunk, Document, DocumentSummary


class InMemoryDocumentRepository:
    """Thread-safe in-memory store for documents and their chunks."""

    def __init__(self) -> None:
        self._documents: dict[UUID, Document] = {}
        self._chunks: dict[UUID, list[Chunk]] = {}  # document_id -> chunks
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    async def create_document(self, document: Document) -> Document:
        """Store a new document record."""
        with self._lock:
            if document.id in self._documents:
                raise ValueError(f"Document {document.id} already exists.")
            stored = document.model_copy(deep=True)
            self._documents[stored.id] = stored
            return stored.model_copy(deep=True)

    async def get_document(self, document_id: UUID) -> Document | None:
        """Retrieve a document by ID."""
        with self._lock:
            doc = self._documents.get(document_id)
            return doc.model_copy(deep=True) if doc else None

    async def list_documents(self) -> list[DocumentSummary]:
        """Return a summary of all ingested documents."""
        with self._lock:
            summaries = [
                DocumentSummary(
                    id=doc.id,
                    filename=doc.filename,
                    page_count=doc.page_count,
                    total_chunks=doc.total_chunks,
                    uploaded_at=doc.uploaded_at,
                )
                for doc in self._documents.values()
            ]
            # Newest first.
            summaries.sort(key=lambda s: s.uploaded_at, reverse=True)
            return summaries

    async def document_count(self) -> int:
        """Return the number of stored documents."""
        with self._lock:
            return len(self._documents)

    # ------------------------------------------------------------------
    # Chunks
    # ------------------------------------------------------------------

    async def save_chunks(self, document_id: UUID, chunks: list[Chunk]) -> int:
        """Store a list of chunks for a document.

        :returns: The number of chunks stored.
        """
        with self._lock:
            if document_id not in self._documents:
                raise KeyError(f"Document {document_id} does not exist.")
            stored = [c.model_copy(deep=True) for c in chunks]
            self._chunks[document_id] = stored
            return len(stored)

    async def get_chunks(self, document_id: UUID) -> list[Chunk]:
        """Retrieve all chunks for a document."""
        with self._lock:
            chunks = self._chunks.get(document_id, [])
            return [c.model_copy(deep=True) for c in chunks]

    async def get_all_chunks(self) -> list[Chunk]:
        """Return every chunk across all documents."""
        with self._lock:
            result: list[Chunk] = []
            for chunks in self._chunks.values():
                result.extend(c.model_copy(deep=True) for c in chunks)
            return result

    async def chunk_count(self) -> int:
        """Return the total number of stored chunks."""
        with self._lock:
            return sum(len(chunks) for chunks in self._chunks.values())

    async def delete_document(self, document_id: UUID) -> bool:
        """Remove a document and its chunks.

        :returns: True if the document existed and was removed.
        """
        with self._lock:
            existed = self._documents.pop(document_id, None) is not None
            self._chunks.pop(document_id, None)
            return existed


__all__ = ["InMemoryDocumentRepository"]
