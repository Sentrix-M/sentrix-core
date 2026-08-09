"""Memory service — stable application API for the Sentrix Memory Layer.

:class:`MemoryService` is the application-layer seam that exposes persistent
memory operations for the six memory types:

- Conversation memory
- Investigation memory
- Report history
- User preferences
- Tool execution history
- Security findings history

It depends only on the :class:`~app.memory.repository.MemoryRepository`
interface, so the storage backend (SQLite today, PostgreSQL/SQLModel later)
is completely hidden. The service also implements the existing
:class:`~app.memory.store.ConversationStore` and
:class:`~app.memory.store.ProjectStore` protocols, making it a drop-in
replacement for the in-memory stores consumed by
:class:`~app.memory.manager.MemoryManager`.
"""

from __future__ import annotations

from typing import Any

from app.memory.models import (
    ConversationMemory,
    MemoryItem,
    ProjectMemory,
)
from app.memory.repository import InMemoryMemoryRepository, MemoryRepository
from app.memory.schemas import (
    ConversationRecord,
    FindingRecord,
    InvestigationRecord,
    PreferenceRecord,
    ReportRecord,
    ToolExecutionRecord,
)


class MemoryService:
    """Stable public API for recording and querying long-term memory.

    :param repository: The storage backend. Defaults to an in-memory
        repository (offline-safe). Pass a
        :class:`~app.memory.repository.SQLiteMemoryRepository` to persist.
    """

    def __init__(self, repository: MemoryRepository | None = None) -> None:
        self._repository = repository or InMemoryMemoryRepository()

    @property
    def repository(self) -> MemoryRepository:
        """The underlying storage repository."""
        return self._repository

    # ------------------------------------------------------------------
    # Conversation memory
    # ------------------------------------------------------------------

    def record_conversation_message(
        self,
        *,
        conversation_id: str,
        content: str,
        role: str = "user",
        org_id: str = "",
        user_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ConversationRecord:
        """Record a single message within a conversation."""
        record = ConversationRecord(
            conversation_id=conversation_id,
            content=content,
            role=role,
            org_id=org_id,
            user_id=user_id,
            metadata=metadata or {},
        )
        return self._repository.add_conversation_message(record)

    def get_conversation_messages(
        self,
        *,
        conversation_id: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[ConversationRecord]:
        """Return conversation messages, newest first."""
        return self._repository.list_conversation_messages(
            conversation_id=conversation_id,
            org_id=org_id,
            user_id=user_id,
            limit=limit,
        )

    def clear_conversation(self, conversation_id: str) -> None:
        """Delete all messages for a conversation."""
        self._repository.clear_conversation(conversation_id)

    # ------------------------------------------------------------------
    # Investigation memory
    # ------------------------------------------------------------------

    def record_investigation(
        self,
        *,
        title: str,
        target: str = "",
        summary: str = "",
        findings: list[dict[str, Any]] | None = None,
        org_id: str = "",
        user_id: str = "",
    ) -> InvestigationRecord:
        """Record a security investigation."""
        record = InvestigationRecord(
            title=title,
            target=target,
            summary=summary,
            findings=findings or [],
            org_id=org_id,
            user_id=user_id,
        )
        return self._repository.add_investigation(record)

    def get_investigations(
        self,
        *,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[InvestigationRecord]:
        """Return investigations, newest first."""
        return self._repository.list_investigations(
            org_id=org_id,
            user_id=user_id,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Report history
    # ------------------------------------------------------------------

    def record_report(
        self,
        *,
        title: str,
        report_format: str = "markdown",
        severity: str = "Medium",
        summary: str = "",
        payload: dict[str, Any] | None = None,
        org_id: str = "",
        user_id: str = "",
    ) -> ReportRecord:
        """Record a generated report."""
        record = ReportRecord(
            title=title,
            report_format=report_format,
            severity=severity,
            summary=summary,
            payload=payload or {},
            org_id=org_id,
            user_id=user_id,
        )
        return self._repository.add_report(record)

    def get_reports(
        self,
        *,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[ReportRecord]:
        """Return reports, newest first."""
        return self._repository.list_reports(
            org_id=org_id,
            user_id=user_id,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # User preferences
    # ------------------------------------------------------------------

    def set_preference(
        self,
        *,
        user_key: str,
        value: str,
        user_id: str,
        org_id: str = "",
    ) -> PreferenceRecord:
        """Upsert a user preference (key scoped to org+user)."""
        record = PreferenceRecord(
            user_key=user_key,
            value=value,
            user_id=user_id,
            org_id=org_id,
        )
        return self._repository.set_preference(record)

    def get_preference(
        self,
        *,
        user_key: str,
        user_id: str,
        org_id: str | None = None,
    ) -> PreferenceRecord | None:
        """Return a single preference, if present."""
        return self._repository.get_preference(
            user_key=user_key,
            user_id=user_id,
            org_id=org_id,
        )

    def get_preferences(
        self,
        *,
        user_id: str | None = None,
        org_id: str | None = None,
        limit: int = 50,
    ) -> list[PreferenceRecord]:
        """Return preferences."""
        return self._repository.list_preferences(
            user_id=user_id,
            org_id=org_id,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Convenience preference helpers (Phase 15B)
    # ------------------------------------------------------------------

    def get_preference_value(
        self,
        *,
        user_key: str,
        user_id: str,
        org_id: str | None = None,
        default: str = "",
    ) -> str:
        """Return a preference value or ``default`` when unset.

        Additive convenience wrapper over :meth:`get_preference` so callers
        (reports, exports) can read a preference without null-handling.
        """
        record = self.get_preference(
            user_key=user_key,
            user_id=user_id,
            org_id=org_id,
        )
        return record.value if record is not None else default

    def get_report_format_preference(
        self,
        *,
        user_id: str,
        default: str = "markdown",
    ) -> str:
        """Return the user's preferred report format (``report_format``)."""
        return self.get_preference_value(
            user_key="report_format",
            user_id=user_id,
            default=default,
        )

    def get_output_style_preference(
        self,
        *,
        user_id: str,
        default: str = "concise",
    ) -> str:
        """Return the user's preferred output style (``output_style``)."""
        return self.get_preference_value(
            user_key="output_style",
            user_id=user_id,
            default=default,
        )

    # ------------------------------------------------------------------
    # Tool execution history
    # ------------------------------------------------------------------

    def record_tool_execution(
        self,
        *,
        tool_name: str,
        success: bool,
        input: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        error: str = "",
        org_id: str = "",
        user_id: str = "",
    ) -> ToolExecutionRecord:
        """Record a single tool execution."""
        record = ToolExecutionRecord(
            tool_name=tool_name,
            success=success,
            input=input or {},
            output=output or {},
            error=error,
            org_id=org_id,
            user_id=user_id,
        )
        return self._repository.add_tool_execution(record)

    def get_tool_executions(
        self,
        *,
        tool_name: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[ToolExecutionRecord]:
        """Return tool executions, newest first."""
        return self._repository.list_tool_executions(
            tool_name=tool_name,
            org_id=org_id,
            user_id=user_id,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Security findings history
    # ------------------------------------------------------------------

    def record_finding(
        self,
        *,
        finding_type: str,
        target: str = "",
        severity: str = "Medium",
        description: str = "",
        detail: dict[str, Any] | None = None,
        org_id: str = "",
        user_id: str = "",
    ) -> FindingRecord:
        """Record a security finding."""
        record = FindingRecord(
            finding_type=finding_type,
            target=target,
            severity=severity,
            description=description,
            detail=detail or {},
            org_id=org_id,
            user_id=user_id,
        )
        return self._repository.add_finding(record)

    def get_findings(
        self,
        *,
        finding_type: str | None = None,
        target: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[FindingRecord]:
        """Return findings, newest first."""
        return self._repository.list_findings(
            finding_type=finding_type,
            target=target,
            org_id=org_id,
            user_id=user_id,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # ConversationStore protocol (MemoryManager integration)
    # ------------------------------------------------------------------

    def append(self, conversation_id: str, item: MemoryItem) -> None:
        """Persist a memory item to the conversation's history."""
        self.record_conversation_message(
            conversation_id=conversation_id,
            content=item.content,
            role=item.role,
            metadata=item.metadata or {},
        )

    def get_history(
        self,
        conversation_id: str,
        *,
        limit: int = 20,
    ) -> ConversationMemory:
        """Return the most recent *limit* items for a conversation."""
        records = self.get_conversation_messages(
            conversation_id=conversation_id,
            limit=limit,
        )
        # Records are newest-first; history is oldest-first.
        items = tuple(
            MemoryItem(
                content=r.content,
                role=r.role,
                timestamp=r.created_at,
                metadata=r.metadata or {},
            )
            for r in reversed(records)
        )
        return ConversationMemory(
            conversation_id=conversation_id,
            history=items,
        )

    # ------------------------------------------------------------------
    # ProjectStore protocol (MemoryManager integration)
    # ------------------------------------------------------------------

    def get(self, project_id: str) -> ProjectMemory:
        """Return the stored context for a project (empty if unknown)."""
        prefs = self.get_preferences(limit=200)
        context = {
            p.user_key: p.value
            for p in prefs
            if p.org_id == project_id or (project_id == "default" and not p.org_id)
        }
        return ProjectMemory(project_id=project_id, context=context)

    def set_context(self, project_id: str, key: str, value: str) -> None:
        """Set a single key-value pair in a project's context."""
        self.set_preference(
            user_key=key,
            value=value,
            user_id="",
            org_id=project_id,
        )

    def clear(self, conversation_id: str | None = None) -> None:
        """Drop stored state.

        :param conversation_id: If given, clears only that conversation's
            history. Otherwise this is a no-op for the persistent service to
            avoid destructive global clears.
        """
        if conversation_id is not None:
            self.clear_conversation(conversation_id)


__all__ = ["MemoryService"]
