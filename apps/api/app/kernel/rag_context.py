"""RAG-aware context provider — bridges the retriever into the kernel pipeline.

``RagAwareContextProvider`` wraps a :class:`ContextProvider` and enriches
every conversation turn with semantically relevant chunks from the vector
store.  The chunks are injected into the :class:`ConversationContext` as
``retrieved_chunks`` and ``citations`` so the prompt builder can include them
in the provider prompt.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.kernel.context_builder import (
    ContextProvider,
    ConversationContext,
    InMemoryContextProvider,
)

if TYPE_CHECKING:
    from app.rag.retriever import SemanticRetriever

logger = logging.getLogger(__name__)

#: Default number of chunks to retrieve per turn.
DEFAULT_TOP_K = 5


class RagAwareContextProvider:
    """Context provider that enriches turns with RAG retrieval.

    Wraps an inner :class:`ContextProvider` (e.g. :class:`InMemoryContextProvider`)
    and, on every ``get_context`` call, performs a semantic search over the
    ingested document store.  The retrieved chunks are attached to the
    :class:`ConversationContext` for downstream use.

    :param inner: The base context provider (history, etc.).  Defaults to a
        fresh :class:`InMemoryContextProvider`.
    :param retriever: The :class:`SemanticRetriever` used for vector search.
        When ``None``, the provider returns the inner context unchanged.
    :param top_k: Number of chunks to retrieve per turn.
    """

    def __init__(
        self,
        inner: ContextProvider | None = None,
        *,
        retriever: SemanticRetriever | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        self._inner = inner or InMemoryContextProvider()
        self._retriever = retriever
        self._top_k = top_k

    # ------------------------------------------------------------------
    # ContextProvider interface
    # ------------------------------------------------------------------

    def get_context(
        self,
        *,
        conversation_id: str,
        message: str,
    ) -> ConversationContext:
        """Build context with RAG enrichment.

        Delegates to the inner context provider for history, then performs
        a semantic search and attaches the results.
        """
        base = self._inner.get_context(
            conversation_id=conversation_id,
            message=message,
        )

        if self._retriever is None:
            return base

        try:
            results = self._retriever.search(query=message, top_k=self._top_k)
        except Exception:  # noqa: BLE001 — retrieval failure must not break the pipeline
            logger.exception("RAG retrieval failed for conversation %s.", conversation_id)
            return base

        if not results:
            return base

        # Convert search results to plain dicts for the context.
        retrieved_chunks: list[dict[str, object]] = []
        citations: list[dict[str, object]] = []

        for result in results:
            chunk_dict: dict[str, object] = {
                "text": result.text,
                "filename": result.filename,
                "page_number": result.page_number,
                "chunk_index": result.chunk_index,
                "score": result.score,
            }
            retrieved_chunks.append(chunk_dict)

            citation_dict: dict[str, object] = {
                "filename": result.filename,
                "page": result.page_number,
                "chunk": str(result.chunk_index),
            }
            citations.append(citation_dict)

        # Return a new context with the RAG data attached.
        return ConversationContext(
            conversation_id=base.conversation_id,
            user_message=base.user_message,
            prior_messages=base.prior_messages,
            retrieved_chunks=tuple(retrieved_chunks),
            citations=tuple(citations),
        )

    def clear(self) -> None:
        """Clear the inner context provider's history."""
        if hasattr(self._inner, "clear"):
            self._inner.clear()


__all__ = ["DEFAULT_TOP_K", "RagAwareContextProvider"]
