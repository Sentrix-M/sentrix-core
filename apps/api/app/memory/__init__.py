"""Sentrix Memory Layer.

Provides a multi-tier memory architecture for the kernel pipeline:

- **Working memory** — the current request (ephemeral, not stored).
- **Conversation memory** — per-conversation message history (in-memory).
- **Project memory** — project-scoped static context (in-memory).
- **Long-term memory** — placeholder interface only (no persistence).

The :class:`MemoryManager` aggregates all tiers and implements the
:class:`~app.kernel.context_builder.ContextProvider` protocol, making it a
drop-in replacement for ``InMemoryContextProvider`` in the kernel pipeline.
"""

from app.memory.manager import MemoryManager
from app.memory.models import (
    ConversationMemory,
    LongTermMemory,
    MemoryContext,
    MemoryItem,
    ProjectMemory,
    WorkingMemory,
)
from app.memory.store import (
    InMemoryConversationStore,
    InMemoryProjectStore,
)
from app.memory.strategy import DefaultMemoryStrategy

__all__ = [
    "ConversationMemory",
    "DefaultMemoryStrategy",
    "InMemoryConversationStore",
    "InMemoryProjectStore",
    "LongTermMemory",
    "MemoryContext",
    "MemoryItem",
    "MemoryManager",
    "ProjectMemory",
    "WorkingMemory",
]
