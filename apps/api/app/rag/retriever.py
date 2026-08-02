"""Semantic retriever for the Sentrix RAG layer.

The retriever orchestrates embedding + vector-store search to return the top-k
most semantically relevant chunks for a given query.  It sits between the
REST API and the vector store, providing a clean application-level interface
that the service layer can call.

No integration with the Gemini kernel is performed at this stage — the
retriever returns raw chunks so the caller can decide how to use them.
"""

from __future__ import annotations

import logging
from typing import Any

from app.rag.embeddings import EmbeddingProvider
from app.rag.vector_store import InMemoryVectorStore, SearchResult, VectorStoreError

logger = logging.getLogger(__name__)


class SemanticRetriever:
    """Semantic search over ingested document chunks.

    :param vector_store: A vector-store instance (in-memory or ChromaDB).
    :param embedding_provider: Embedding provider.  Defaults to a fresh
        :class:`~app.rag.embeddings.EmbeddingProvider`.
    """

    def __init__(
        self,
        vector_store: InMemoryVectorStore | None = None,
        *,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._vector_store = vector_store or InMemoryVectorStore(
            embedding_provider=embedding_provider,
        )
        self._embedding_provider = embedding_provider or EmbeddingProvider()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """Generate embeddings for a list of chunks and store them.

        :param chunks: List of chunk dicts with keys ``id``, ``document_id``,
            ``text``, ``filename``, ``page_number``, ``chunk_index``.
        :returns: The number of chunks indexed.
        """
        return self._vector_store.add_chunks(chunks)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Return the top-k most semantically relevant chunks for ``query``.

        :param query: Natural-language search query.
        :param top_k: Number of results to return (default 5).
        :returns: Ordered list of :class:`SearchResult`.
        :raises VectorStoreError: If the underlying store fails.
        """
        if not query or not query.strip():
            return []

        try:
            results = self._vector_store.search(query, top_k=top_k)
        except VectorStoreError:
            raise
        except Exception as exc:
            logger.exception("Semantic search failed.")
            raise VectorStoreError(f"Search failed: {exc}") from exc

        return results

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all indexed entries (for testing)."""
        if hasattr(self._vector_store, "clear"):
            self._vector_store.clear()


__all__ = ["SemanticRetriever"]
