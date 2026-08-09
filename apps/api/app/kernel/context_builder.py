"""Conversation context collection for the Sentrix Kernel.

``ContextBuilder`` gathers everything needed to respond to a turn: the current
user message and any prior messages in the conversation. The kernel does not
persist state — callers provide the history they have, and the context builder
normalizes it into a provider-agnostic structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ContextMessage:
    """A single message in a conversation."""

    role: str
    content: str
    timestamp: datetime | None = None


@dataclass(frozen=True)
class ConversationContext:
    """The normalized context for one kernel turn."""

    conversation_id: str
    user_message: ContextMessage
    prior_messages: tuple[ContextMessage, ...] = field(default_factory=tuple)
    retrieved_chunks: tuple[dict[str, object], ...] = field(default_factory=tuple)
    citations: tuple[dict[str, object], ...] = field(default_factory=tuple)


class ContextProvider(Protocol):
    """Interface for components that supply conversation history."""

    def get_context(
        self,
        *,
        conversation_id: str,
        message: str,
    ) -> ConversationContext:
        """Return the assembled context for a conversation turn."""
        ...


class InMemoryContextProvider:
    """In-memory context provider for development and testing.

    Retains no durable state (see ``clear``) and is intentionally unsuitable
    for production persistence — it exists so the pipeline can run without a
    database and so tests can exercise the full flow deterministically.
    """

    def __init__(self, history_limit: int = 20) -> None:
        self._history: dict[str, list[ContextMessage]] = {}
        self._history_limit = history_limit

    def get_context(
        self,
        *,
        conversation_id: str,
        message: str,
    ) -> ConversationContext:
        """Build context for ``message`` in ``conversation_id``."""
        history = self._history.setdefault(conversation_id, [])
        prior = tuple(history)
        current = ContextMessage(
            role="user",
            content=message,
            timestamp=datetime.now(),
        )
        # Append the current message so the next turn sees it as history.
        history.append(current)
        # Keep only the most recent N messages.
        if len(history) > self._history_limit:
            del history[: len(history) - self._history_limit]
        return ConversationContext(
            conversation_id=conversation_id,
            user_message=current,
            prior_messages=prior,
        )

    def clear(self) -> None:
        """Drop all in-memory history (used by tests)."""
        self._history.clear()


class ContextBuilder(ContextProvider, Protocol):
    """Alias of :class:`ContextProvider` for readability in the pipeline."""


__all__ = [
    "ContextBuilder",
    "ContextMessage",
    "ContextProvider",
    "ConversationContext",
    "InMemoryContextProvider",
]
