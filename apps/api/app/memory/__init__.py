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
from app.memory.repository import (
    InMemoryMemoryRepository,
    MemoryRepository,
    SQLiteMemoryRepository,
)
from app.memory.retriever import (
    MemoryRetriever,
    RecallResponse,
    RecallResult,
)
from app.memory.schemas import (
    ConversationRecord,
    FindingRecord,
    InvestigationRecord,
    PreferenceRecord,
    ReportRecord,
    ToolExecutionRecord,
)
from app.memory.service import MemoryService
from app.memory.store import (
    InMemoryConversationStore,
    InMemoryProjectStore,
)
from app.memory.strategy import DefaultMemoryStrategy

__all__ = [
    "ConversationMemory",
    "ConversationRecord",
    "DefaultMemoryStrategy",
    "FindingRecord",
    "InMemoryConversationStore",
    "InMemoryMemoryRepository",
    "InMemoryProjectStore",
    "InvestigationRecord",
    "LongTermMemory",
    "MemoryContext",
    "MemoryItem",
    "MemoryManager",
    "MemoryRepository",
    "MemoryRetriever",
    "MemoryService",
    "PreferenceRecord",
    "ProjectMemory",
    "RecallResponse",
    "RecallResult",
    "ReportRecord",
    "SQLiteMemoryRepository",
    "ToolExecutionRecord",
    "WorkingMemory",
]
