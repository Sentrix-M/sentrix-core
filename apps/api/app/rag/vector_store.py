"""Vector store backed by ChromaDB for the Sentrix RAG layer.

Stores chunk embeddings alongside their metadata (text, filename, page
number, chunk index, document ID) and provides similarity search.

When ChromaDB is not available or the API key is missing, a lightweight
in-memory fallback (``InMemoryVectorStore``) is used so the platform
never breaks during development or testing.
"""

from __future__ import annotations

import contextlib
import logging
import math
import uuid as uuid_lib
from collections.abc import Sequence
from typing import Any

from app.rag.embeddings import EMBEDDING_DIMENSIONS, EmbeddingProvider

logger = logging.getLogger(__name__)

#: Default ChromaDB collection name for RAG chunks.
DEFAULT_COLLECTION = "sentrix_chunks"


class VectorStoreError(Exception):
    """Raised when a vector-store operation fails."""


# ---------------------------------------------------------------------------
# Data class for search results
# ---------------------------------------------------------------------------


class SearchResult:
    """A single search result with metadata."""

    def __init__(
        self,
        *,
        chunk_id: str,
        document_id: str,
        text: str,
        filename: str,
        page_number: int,
        chunk_index: int,
        score: float,
    ) -> None:
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.text = text
        self.filename = filename
        self.page_number = page_number
        self.chunk_index = chunk_index
        self.score = score

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "text": self.text,
            "filename": self.filename,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "score": self.score,
        }


# ---------------------------------------------------------------------------
# ChromaDB-backed vector store
# ---------------------------------------------------------------------------


class ChromaVectorStore:
    """ChromaDB-backed vector store for RAG chunk embeddings.

    :param collection_name: ChromaDB collection name.
    :param embedding_provider: Embedding provider instance.
    :param persist_directory: Optional directory for persistent storage.
        When ``None``, ChromaDB runs in-memory only.
    """

    def __init__(
        self,
        *,
        collection_name: str = DEFAULT_COLLECTION,
        embedding_provider: EmbeddingProvider | None = None,
        persist_directory: str | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider or EmbeddingProvider()
        self._collection_name = collection_name
        self._persist_directory = persist_directory
        self._collection = None
        self._client = None

    # ------------------------------------------------------------------
    # Lazy initialisation
    # ------------------------------------------------------------------

    @property
    def _chroma_collection(self):
        """Lazily create and return the ChromaDB collection."""
        if self._collection is not None:
            return self._collection

        try:
            import chromadb
        except ImportError:
            raise VectorStoreError(
                "chromadb is not installed. Install it with: pip install chromadb"
            ) from None

        try:
            if self._persist_directory:
                self._client = chromadb.PersistentClient(
                    path=self._persist_directory,
                )
            else:
                self._client = chromadb.EphemeralClient()

            # Delete the collection if it already exists to start clean.
            # (In production you would want to reuse it.)
            with contextlib.suppress(Exception):
                self._client.delete_collection(self._collection_name)

            self._collection = self._client.create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "Created ChromaDB collection '%s' (dim=%d, persist=%s).",
                self._collection_name,
                EMBEDDING_DIMENSIONS,
                self._persist_directory or "ephemeral",
            )
        except Exception as exc:
            raise VectorStoreError(f"Failed to initialise ChromaDB: {exc}") from exc

        return self._collection

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> int:
        """Add chunks with embeddings to the vector store.

        Each dict in ``chunks`` must have keys:
        ``id``, ``document_id``, ``text``, ``filename``, ``page_number``,
        ``chunk_index``.

        :returns: The number of chunks added.
        """
        if not chunks:
            return 0

        texts = [c["text"] for c in chunks]
        embeddings = self._embedding_provider.embed_batch(texts)

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        embeds: list[list[float]] = []

        for chunk, emb in zip(chunks, embeddings, strict=False):
            cid = str(chunk.get("id", uuid_lib.uuid4()))
            ids.append(cid)
            documents.append(chunk["text"])
            metadatas.append(
                {
                    "document_id": str(chunk["document_id"]),
                    "filename": chunk["filename"],
                    "page_number": chunk["page_number"],
                    "chunk_index": chunk["chunk_index"],
                }
            )
            embeds.append(emb)

        self._chroma_collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeds,
        )

        logger.debug("Added %d chunks to vector store.", len(chunks))
        return len(chunks)

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Semantic search over stored chunks.

        :param query: The search query string.
        :param top_k: Number of top results to return.
        :returns: A list of :class:`SearchResult` ordered by relevance.
        """
        query_embedding = self._embedding_provider.embed(query)

        results = self._chroma_collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        return self._build_results(results)

    def search_by_text(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Search using text-based embedding (auto-embedded by ChromaDB).

        This method lets ChromaDB compute the embedding from the query text
        directly, which is useful when the embedding provider is registered
        with ChromaDB's embedding function.  For now we always use the
        separate embedding provider so the two paths are consistent.
        """
        return self.search(query, top_k=top_k)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_results(
        raw: dict[str, Any],
    ) -> list[SearchResult]:
        """Convert raw ChromaDB query output into ``SearchResult`` objects."""
        results: list[SearchResult] = []

        ids = raw.get("ids", [[]])[0]
        documents = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        if not ids:
            return results

        for i in range(len(ids)):
            meta = metadatas[i] if i < len(metadatas) else {}
            # ChromaDB returns cosine distance (0 = identical); convert to
            # a similarity score (1 = identical).
            distance = distances[i] if i < len(distances) else 1.0
            score = 1.0 - distance

            results.append(
                SearchResult(
                    chunk_id=ids[i],
                    document_id=meta.get("document_id", ""),
                    text=documents[i] if i < len(documents) else "",
                    filename=meta.get("filename", ""),
                    page_number=int(meta.get("page_number", 0)),
                    chunk_index=int(meta.get("chunk_index", 0)),
                    score=max(0.0, score),
                )
            )

        # Sort by score descending.
        results.sort(key=lambda r: r.score, reverse=True)
        return results


# ---------------------------------------------------------------------------
# In-memory fallback vector store (for testing / development)
# ---------------------------------------------------------------------------


class InMemoryVectorStore:
    """Lightweight in-memory vector store with cosine-similarity search.

    Used when ChromaDB is not available or for deterministic testing.
    """

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider or EmbeddingProvider()
        self._entries: list[dict[str, Any]] = []

    def add_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> int:
        """Add chunks with embeddings to the in-memory store."""
        if not chunks:
            return 0

        texts = [c["text"] for c in chunks]
        embeddings = self._embedding_provider.embed_batch(texts)

        for chunk, emb in zip(chunks, embeddings, strict=False):
            self._entries.append(
                {
                    "id": str(chunk.get("id", uuid_lib.uuid4())),
                    "document_id": str(chunk["document_id"]),
                    "text": chunk["text"],
                    "filename": chunk["filename"],
                    "page_number": chunk["page_number"],
                    "chunk_index": chunk["chunk_index"],
                    "embedding": emb,
                }
            )

        return len(chunks)

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Semantic search using cosine similarity."""
        if not self._entries:
            return []

        query_embedding = self._embedding_provider.embed(query)

        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in self._entries:
            score = self._cosine_similarity(query_embedding, entry["embedding"])
            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        results: list[SearchResult] = []
        for score, entry in top:
            results.append(
                SearchResult(
                    chunk_id=entry["id"],
                    document_id=entry["document_id"],
                    text=entry["text"],
                    filename=entry["filename"],
                    page_number=entry["page_number"],
                    chunk_index=entry["chunk_index"],
                    score=score,
                )
            )
        return results

    @staticmethod
    def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def clear(self) -> None:
        """Remove all entries."""
        self._entries.clear()

    @property
    def count(self) -> int:
        """Return the number of stored entries."""
        return len(self._entries)


__all__ = [
    "ChromaVectorStore",
    "DEFAULT_COLLECTION",
    "InMemoryVectorStore",
    "SearchResult",
    "VectorStoreError",
]
