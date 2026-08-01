"""MemoryManager — aggregates all memory tiers into a kernel context.

The :class:`MemoryManager` implements the :class:`ContextProvider` protocol
from the kernel, which means it can be injected into
:class:`~app.kernel.pipeline.KernelPipeline` as a drop-in replacement for
``InMemoryContextProvider``.

For each turn it:

1. Captures the current message as **working memory** (ephemeral).
2. Loads prior **conversation memory** from the in-memory store.
3. Loads **project memory** for the inferred project.
4. Attempts **long-term memory** (currently a no-op placeholder).
5. Applies the configured **memory strategy** for compaction.
6. Converts the aggregated :class:`MemoryContext` into a kernel
   :class:`~app.kernel.context_builder.ConversationContext`.
7. Persists the current turn to the conversation store for future turns.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.kernel.context_builder import ContextMessage, ConversationContext
from app.memory.models import (
    LongTermMemory,
    MemoryContext,
    MemoryItem,
    ProjectMemory,
    WorkingMemory,
)
from app.memory.store import InMemoryConversationStore, InMemoryProjectStore
from app.memory.strategy import DefaultMemoryStrategy, MemoryStrategy


class MemoryManager:
    """Aggregate multiple memory tiers into a single kernel context.

    :param conversation_store: Store for conversation history. Defaults to
        a fresh :class:`InMemoryConversationStore`.
    :param project_store: Store for project context. Defaults to a fresh
        :class:`InMemoryProjectStore`.
    :param strategy: Optional compaction strategy. Defaults to
        :class:`DefaultMemoryStrategy` (pass-through).
    :param history_limit: Maximum number of prior messages to include in
        the context.  Defaults to 20.
    """

    def __init__(
        self,
        conversation_store: InMemoryConversationStore | None = None,
        project_store: InMemoryProjectStore | None = None,
        strategy: MemoryStrategy | None = None,
        history_limit: int = 20,
    ) -> None:
        self._conversation_store = conversation_store or InMemoryConversationStore(
            history_limit=history_limit,
        )
        self._project_store = project_store or InMemoryProjectStore()
        self._strategy = strategy or DefaultMemoryStrategy()
        self._history_limit = history_limit

    # ------------------------------------------------------------------
    # ContextProvider protocol implementation
    # ------------------------------------------------------------------

    def get_context(
        self,
        *,
        conversation_id: str,
        message: str,
    ) -> ConversationContext:
        """Assemble the full memory context for a single kernel turn.

        :param conversation_id: Client-generated conversation identifier.
        :param message: The user's current message.
        :returns: A :class:`ConversationContext` ready for the kernel.
        """
        # 1. Working memory — current turn, not persisted.
        working = WorkingMemory(message=message)

        # 2. Conversation memory — prior turns from the store.
        conversation = self._conversation_store.get_history(
            conversation_id,
            limit=self._history_limit,
        )

        # 3. Project memory — inferred from conversation_id.
        project = self._resolve_project(conversation_id)

        # 4. Long-term memory — placeholder.
        long_term = self._resolve_long_term()

        # 5. Aggregate & apply strategy.
        memory_context = MemoryContext(
            working=working,
            conversation=conversation,
            project=project,
            long_term=long_term,
        )
        memory_context = self._strategy.compact(memory_context)

        # 6. Convert to kernel ConversationContext.
        prior = tuple(
            ContextMessage(
                role=item.role,
                content=item.content,
                timestamp=item.timestamp,
            )
            for item in memory_context.conversation.history
        )
        now = datetime.now(timezone.utc)
        current = ContextMessage(
            role="user",
            content=message,
            timestamp=now,
        )

        # 7. Persist the current turn for future turns.
        self._conversation_store.append(
            conversation_id,
            MemoryItem(
                content=message,
                role="user",
                timestamp=now,
            ),
        )

        return ConversationContext(
            conversation_id=conversation_id,
            user_message=current,
            prior_messages=prior,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_project(self, conversation_id: str) -> ProjectMemory:
        """Infer the project from the conversation identifier.

        Conventions:

        - ``proj-<id>`` / ``project-<id>`` → project = ``<id>``
        - ``conv-<id>`` → project = ``default``
        """
        for prefix in ("proj-", "project-"):
            if conversation_id.startswith(prefix):
                project_id = conversation_id.removeprefix(prefix)
                return self._project_store.get(project_id)
        return self._project_store.get("default")

    @staticmethod
    def _resolve_long_term() -> LongTermMemory:
        """Return a no-op long-term memory placeholder.

        Replace this method when a real long-term store is implemented.
        """
        return LongTermMemory()

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def clear(self, conversation_id: str | None = None) -> None:
        """Drop in-memory state.

        :param conversation_id: If given, clears only that conversation's
            history.  Otherwise clears all conversation history.
        """
        self._conversation_store.clear(conversation_id)

    @property
    def conversation_store(self) -> InMemoryConversationStore:
        """Access the underlying conversation store (for testing/seed)."""
        return self._conversation_store

    @property
    def project_store(self) -> InMemoryProjectStore:
        """Access the underlying project store (for testing/seed)."""
        return self._project_store


__all__ = ["MemoryManager"]
