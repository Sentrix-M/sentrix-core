"""Memory data models for the Sentrix Memory Layer.

Each model represents a distinct memory tier with the narrowest possible
interface. All models are frozen dataclasses — once created they are
immutable, which makes them safe to pass across the kernel boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MemoryItem:
    """A single entry in a memory store.

    :param content: The text content of the memory.
    :param role: Speaker role (``user``, ``assistant``, ``system``).
    :param timestamp: When the memory was recorded.
    :param metadata: Extensible key-value metadata bag.
    """

    content: str
    role: str = "user"
    timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkingMemory:
    """Current request context — present-turn only, not persisted.

    :param message: The raw user message for this turn.
    :param intent: Optional inferred intent label.
    :param entities: Optional extracted entities from the message.
    """

    message: str
    intent: str | None = None
    entities: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConversationMemory:
    """Conversation-scoped memory — the history of a single conversation.

    :param conversation_id: Identifies the conversation.
    :param history: Ordered prior messages (most recent last).
    """

    conversation_id: str
    history: tuple[MemoryItem, ...] = ()


@dataclass(frozen=True)
class ProjectMemory:
    """Project-scoped static context.

    Holds key-value context for the active project (e.g. environment,
    asset inventory, compliance baseline).  All values are plain strings
    so the store stays trivial; richer structures can be serialised by
    the caller.

    :param project_id: Identifies the project.
    :param context: Key-value map of project context.
    """

    project_id: str
    context: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LongTermMemory:
    """Placeholder for long-term memory.

    No database, no vector store, no embeddings — this is a stub that
    will be replaced by a real implementation in a future phase.

    :param summary: Optional summary of long-term knowledge.
    :param tags: Optional tags for categorisation.
    """

    summary: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryContext:
    """Aggregated snapshot of all memory tiers for a single kernel turn.

    :param working: Current-turn working memory.
    :param conversation: Conversation history.
    :param project: Project-scoped context.
    :param long_term: Long-term memory (placeholder).
    """

    working: WorkingMemory
    conversation: ConversationMemory
    project: ProjectMemory = ProjectMemory(project_id="default")
    long_term: LongTermMemory = LongTermMemory()


__all__ = [
    "ConversationMemory",
    "LongTermMemory",
    "MemoryContext",
    "MemoryItem",
    "ProjectMemory",
    "WorkingMemory",
]
