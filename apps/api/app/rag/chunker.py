"""Text chunker — splits cleaned document text into configurable chunks.

The chunker operates on a per-page basis, producing chunks that never span
page boundaries so each chunk retains a stable ``page_number`` reference.
Chunks are produced with configurable overlap for continuity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.rag.parser import ParsedDocument
from app.rag.schemas import Chunk

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkingConfig:
    """Configuration for the text chunker.

    Defaults are tuned for cybersecurity documents (reports, IR guides,
    threat intel) where paragraphs are often dense and technical.
    """

    #: Target chunk size in characters (not tokens — no tokeniser yet).
    chunk_size: int = 1500

    #: Overlap between consecutive chunks (characters).
    chunk_overlap: int = 150

    #: Minimum chunk length; shorter chunks are discarded unless they are
    #: the only chunk on a page.
    min_chunk_length: int = 50


class TextChunker:
    """Split parsed document pages into :class:`Chunk` instances.

    Usage::

        chunker = TextChunker()
        config = ChunkingConfig(chunk_size=1000, chunk_overlap=100)
        chunks = chunker.chunk(parsed_doc, config=config)
    """

    DEFAULT_CONFIG = ChunkingConfig()

    def chunk(
        self,
        document: ParsedDocument,
        *,
        config: ChunkingConfig | None = None,
        document_id: object | None = None,
    ) -> list[Chunk]:
        """Split ``document`` into a list of chunks.

        :param document: Parsed document with cleaned pages.
        :param config: Chunking configuration; defaults to
            :attr:`DEFAULT_CONFIG`.
        :param document_id: Optional document UUID to associate with each
            chunk. When omitted, a placeholder UUID is used (caller should
            set the real ID when persisting).
        :returns: A flat list of :class:`Chunk` instances.
        """
        cfg = config or self.DEFAULT_CONFIG
        import uuid  # noqa: PLC0415 - lazy import

        doc_id = document_id or uuid.uuid4()

        chunks: list[Chunk] = []
        global_chunk_index = 0

        for page in document.pages:
            page_chunks = self._split_page(
                text=page.text,
                page_number=page.page_number,
                document_id=doc_id,
                filename=document.filename,
                config=cfg,
                start_index=global_chunk_index,
            )
            chunks.extend(page_chunks)
            global_chunk_index += len(page_chunks)

        logger.debug(
            "Chunked '%s' (%d pages) into %d chunks.",
            document.filename,
            document.page_count,
            len(chunks),
        )
        return chunks

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _split_page(
        *,
        text: str,
        page_number: int,
        document_id: object,
        filename: str,
        config: ChunkingConfig,
        start_index: int,
    ) -> list[Chunk]:
        """Split a single page's text into chunks."""
        import uuid  # noqa: PLC0415

        if len(text) <= config.min_chunk_length:
            # Page is too short to split; return a single chunk.
            return [
                Chunk(
                    id=uuid.uuid4(),
                    document_id=document_id,  # type: ignore[arg-type]
                    text=text,
                    page_number=page_number,
                    chunk_index=start_index,
                    filename=filename,
                )
            ]

        chunks: list[Chunk] = []
        size = config.chunk_size
        overlap = config.chunk_overlap
        step = size - overlap
        pos = 0

        while pos < len(text):
            end = min(pos + size, len(text))
            chunk_text = text[pos:end].strip()

            if chunk_text and len(chunk_text) >= config.min_chunk_length:
                chunks.append(
                    Chunk(
                        id=uuid.uuid4(),
                        document_id=document_id,  # type: ignore[arg-type]
                        text=chunk_text,
                        page_number=page_number,
                        chunk_index=start_index + len(chunks),
                        filename=filename,
                    )
                )
            elif chunk_text and not chunks:
                # First chunk is below min length — emit it anyway.
                chunks.append(
                    Chunk(
                        id=uuid.uuid4(),
                        document_id=document_id,  # type: ignore[arg-type]
                        text=chunk_text,
                        page_number=page_number,
                        chunk_index=start_index,
                        filename=filename,
                    )
                )

            if end >= len(text):
                break
            pos += step

        return chunks


__all__ = [
    "ChunkingConfig",
    "TextChunker",
]
