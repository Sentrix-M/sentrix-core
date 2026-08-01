"""In-memory memory stores for the Sentrix Memory Layer.

No persistence, no database, no vector store — all data lives in Python
dictionaries and is lost on process restart.  This is intentional: the
stores exist so the full pipeline can be exercised offline and in tests
without infrastructure.

Each store exposes a narrow protocol so a future real implementation
(e.g. Redis or PostgreSQL) can be swapped in without changing the
:class:`~app.memory.manager.MemoryManager`.
"""

from __future__ import annotations

from typing import Protocol

from app.memory.models import ConversationMemory, MemoryItem, ProjectMemory


class ConversationStore(Protocol):
    """Protocol for conversation-memory storage."""

    def append(self, conversation_id: str, item: MemoryItem) -> None:
        """Persist a memory item to the conversation's history."""

    def get_history(
        self,
        conversation_id: str,
        *,
        limit: int = 20,
    ) -> ConversationMemory:
        """Return the most recent *limit* items for a conversation."""

    def clear(self, conversation_id: str | None = None) -> None:
        """Drop history for one conversation, or all if *conversation_id* is
        ``None``."""


class ProjectStore(Protocol):
    """Protocol for project-memory storage."""

    def get(self, project_id: str) -> ProjectMemory:
        """Return the stored context for a project."""

    def set_context(self, project_id: str, key: str, value: str) -> None:
        """Set a single key-value pair in a project's context."""

    def clear(self, project_id: str | None = None) -> None:
        """Drop project context for one project, or all if *project_id* is
        ``None``."""


class InMemoryConversationStore:
    """Conversation store backed by an in-memory dictionary.

    Retains a configurable history limit per conversation.  Oldest entries
    are evicted first when the limit is exceeded.
    """

    def __init__(self, history_limit: int = 20) -> None:
        """Create an empty store.

        :param history_limit: Maximum number of items retained per
            conversation.
        """
        self._store: dict[str, list[MemoryItem]] = {}
        self._history_limit = history_limit

    def append(self, conversation_id: str, item: MemoryItem) -> None:
        """Append *item* to the conversation's history, evicting old entries
        if the history limit would be exceeded."""
        history = self._store.setdefault(conversation_id, [])
        history.append(item)
        if len(history) > self._history_limit:
            del history[: len(history) - self._history_limit]

    def get_history(
        self,
        conversation_id: str,
        *,
        limit: int = 20,
    ) -> ConversationMemory:
        """Return the most recent *limit* items (or all, whichever is
        smaller)."""
        history = tuple(self._store.get(conversation_id, [])[-limit:])
        return ConversationMemory(
            conversation_id=conversation_id,
            history=history,
        )

    def clear(self, conversation_id: str | None = None) -> None:
        """Drop history for one conversation, or all if ``None``."""
        if conversation_id is not None:
            self._store.pop(conversation_id, None)
        else:
            self._store.clear()

    @property
    def history_limit(self) -> int:
        """The configured maximum history length per conversation."""
        return self._history_limit


class InMemoryProjectStore:
    """Project store backed by an in-memory dictionary.

    Each project holds a flat ``dict[str, str]`` of context keys.  No
    nesting, no persistence — just enough for offline and test use.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, str]] = {}

    def get(self, project_id: str) -> ProjectMemory:
        """Return the stored context for *project_id* (empty if unknown)."""
        context = self._store.get(project_id, {})
        return ProjectMemory(
            project_id=project_id,
            context=dict(context),
        )

    def set_context(self, project_id: str, key: str, value: str) -> None:
        """Set *key* to *value* in the project's context map."""
        ctx = self._store.setdefault(project_id, {})
        ctx[key] = value

    def clear(self, project_id: str | None = None) -> None:
        """Drop project context for one project, or all if ``None``."""
        if project_id is not None:
            self._store.pop(project_id, None)
        else:
            self._store.clear()


__all__ = [
    "ConversationStore",
    "InMemoryConversationStore",
    "InMemoryProjectStore",
    "ProjectStore",
]
