"""Memory repository — storage abstraction for the Sentrix Memory Layer.

:class:`MemoryRepository` defines the stable interface that
:class:`~app.memory.service.MemoryService` depends on. Concretes:

- :class:`SQLiteMemoryRepository` — persists to a SQLite database via the
  stdlib ``sqlite3`` driver (:class:`~app.db.db.MemoryDatabase`).
- :class:`InMemoryMemoryRepository` — keeps everything in Python memory
  (used by tests and the default offline flow).

Because the service depends only on the interface, swapping the storage
backend (e.g. to PostgreSQL/SQLModel later) requires changing only the
repository implementation — no public API changes.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from app.db.db import MemoryDatabase, dumps, loads
from app.memory.schemas import (
    ConversationRecord,
    FindingRecord,
    InvestigationRecord,
    PreferenceRecord,
    ReportRecord,
    ToolExecutionRecord,
)


def _iso(value: datetime | None) -> str:
    """Serialize a datetime to ISO-8601 (or empty string when None)."""
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string back into a timezone-aware datetime."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class MemoryRepository(ABC):
    """Stable interface for all memory storage backends."""

    # ------------------------------------------------------------------
    # Conversation memory
    # ------------------------------------------------------------------

    @abstractmethod
    def add_conversation_message(self, record: ConversationRecord) -> ConversationRecord:
        """Persist a single conversation message."""

    @abstractmethod
    def list_conversation_messages(
        self,
        *,
        conversation_id: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[ConversationRecord]:
        """Return conversation messages, newest first."""

    @abstractmethod
    def clear_conversation(self, conversation_id: str) -> None:
        """Delete all messages for a conversation."""

    # ------------------------------------------------------------------
    # Investigation memory
    # ------------------------------------------------------------------

    @abstractmethod
    def add_investigation(self, record: InvestigationRecord) -> InvestigationRecord:
        """Persist a security investigation."""

    @abstractmethod
    def list_investigations(
        self,
        *,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[InvestigationRecord]:
        """Return investigations, newest first."""

    # ------------------------------------------------------------------
    # Report history
    # ------------------------------------------------------------------

    @abstractmethod
    def add_report(self, record: ReportRecord) -> ReportRecord:
        """Persist a generated report."""

    @abstractmethod
    def list_reports(
        self,
        *,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[ReportRecord]:
        """Return reports, newest first."""

    # ------------------------------------------------------------------
    # User preferences
    # ------------------------------------------------------------------

    @abstractmethod
    def set_preference(self, record: PreferenceRecord) -> PreferenceRecord:
        """Upsert a user preference (key scoped to org+user)."""

    @abstractmethod
    def get_preference(
        self,
        *,
        user_id: str,
        user_key: str,
        org_id: str | None = None,
    ) -> PreferenceRecord | None:
        """Return a single preference, if present."""

    @abstractmethod
    def list_preferences(
        self,
        *,
        user_id: str | None = None,
        org_id: str | None = None,
        limit: int = 50,
    ) -> list[PreferenceRecord]:
        """Return preferences."""

    # ------------------------------------------------------------------
    # Tool execution history
    # ------------------------------------------------------------------

    @abstractmethod
    def add_tool_execution(self, record: ToolExecutionRecord) -> ToolExecutionRecord:
        """Persist a single tool execution."""

    @abstractmethod
    def list_tool_executions(
        self,
        *,
        tool_name: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[ToolExecutionRecord]:
        """Return tool executions, newest first."""

    # ------------------------------------------------------------------
    # Security findings history
    # ------------------------------------------------------------------

    @abstractmethod
    def add_finding(self, record: FindingRecord) -> FindingRecord:
        """Persist a security finding."""

    @abstractmethod
    def list_findings(
        self,
        *,
        finding_type: str | None = None,
        target: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[FindingRecord]:
        """Return findings, newest first."""


class InMemoryMemoryRepository(MemoryRepository):
    """In-memory implementation used by tests and the default offline flow."""

    def __init__(self) -> None:
        self._conversations: list[ConversationRecord] = []
        self._investigations: list[InvestigationRecord] = []
        self._reports: list[ReportRecord] = []
        self._preferences: dict[tuple[str, str, str], PreferenceRecord] = {}
        self._tool_executions: list[ToolExecutionRecord] = []
        self._findings: list[FindingRecord] = []

    # ------------------------------------------------------------------
    # Conversation memory
    # ------------------------------------------------------------------

    def add_conversation_message(self, record: ConversationRecord) -> ConversationRecord:
        self._conversations.append(record)
        return record

    def list_conversation_messages(
        self,
        *,
        conversation_id: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[ConversationRecord]:
        items = [
            r
            for r in self._conversations
            if (conversation_id is None or r.conversation_id == conversation_id)
            and (org_id is None or r.org_id == org_id)
            and (user_id is None or r.user_id == user_id)
        ]
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items[:limit]

    def clear_conversation(self, conversation_id: str) -> None:
        self._conversations = [
            r for r in self._conversations if r.conversation_id != conversation_id
        ]

    # ------------------------------------------------------------------
    # Investigation memory
    # ------------------------------------------------------------------

    def add_investigation(self, record: InvestigationRecord) -> InvestigationRecord:
        self._investigations.append(record)
        return record

    def list_investigations(
        self,
        *,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[InvestigationRecord]:
        items = [
            r
            for r in self._investigations
            if (org_id is None or r.org_id == org_id)
            and (user_id is None or r.user_id == user_id)
        ]
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items[:limit]

    # ------------------------------------------------------------------
    # Report history
    # ------------------------------------------------------------------

    def add_report(self, record: ReportRecord) -> ReportRecord:
        self._reports.append(record)
        return record

    def list_reports(
        self,
        *,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[ReportRecord]:
        items = [
            r
            for r in self._reports
            if (org_id is None or r.org_id == org_id)
            and (user_id is None or r.user_id == user_id)
        ]
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items[:limit]

    # ------------------------------------------------------------------
    # User preferences
    # ------------------------------------------------------------------

    def set_preference(self, record: PreferenceRecord) -> PreferenceRecord:
        key = (record.org_id, record.user_id, record.user_key)
        self._preferences[key] = record
        return record

    def get_preference(
        self,
        *,
        user_id: str,
        user_key: str,
        org_id: str | None = None,
    ) -> PreferenceRecord | None:
        return self._preferences.get((org_id or "", user_id, user_key))

    def list_preferences(
        self,
        *,
        user_id: str | None = None,
        org_id: str | None = None,
        limit: int = 50,
    ) -> list[PreferenceRecord]:
        items = [
            r
            for r in self._preferences.values()
            if (user_id is None or r.user_id == user_id)
            and (org_id is None or r.org_id == org_id)
        ]
        items.sort(key=lambda r: r.updated_at, reverse=True)
        return items[:limit]

    # ------------------------------------------------------------------
    # Tool execution history
    # ------------------------------------------------------------------

    def add_tool_execution(self, record: ToolExecutionRecord) -> ToolExecutionRecord:
        self._tool_executions.append(record)
        return record

    def list_tool_executions(
        self,
        *,
        tool_name: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[ToolExecutionRecord]:
        items = [
            r
            for r in self._tool_executions
            if (tool_name is None or r.tool_name == tool_name)
            and (org_id is None or r.org_id == org_id)
            and (user_id is None or r.user_id == user_id)
        ]
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items[:limit]

    # ------------------------------------------------------------------
    # Security findings history
    # ------------------------------------------------------------------

    def add_finding(self, record: FindingRecord) -> FindingRecord:
        self._findings.append(record)
        return record

    def list_findings(
        self,
        *,
        finding_type: str | None = None,
        target: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[FindingRecord]:
        items = [
            r
            for r in self._findings
            if (finding_type is None or r.finding_type == finding_type)
            and (target is None or r.target == target)
            and (org_id is None or r.org_id == org_id)
            and (user_id is None or r.user_id == user_id)
        ]
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items[:limit]


class SQLiteMemoryRepository(MemoryRepository):
    """SQLite-backed implementation using the stdlib ``sqlite3`` driver.

    :param db: A :class:`~app.db.db.MemoryDatabase` instance. When omitted, a
        transient in-memory database is created.
    """

    def __init__(self, db: MemoryDatabase | None = None) -> None:
        self._db = db or MemoryDatabase()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Conversation memory
    # ------------------------------------------------------------------

    def add_conversation_message(self, record: ConversationRecord) -> ConversationRecord:
        with self._lock:
            self._db.insert(
                "conversations",
                {
                    "id": record.id,
                    "org_id": record.org_id,
                    "user_id": record.user_id,
                    "conversation_id": record.conversation_id,
                    "role": record.role,
                    "content": record.content,
                    "metadata": dumps(record.metadata),
                    "created_at": _iso(record.created_at),
                },
            )
        return record

    def list_conversation_messages(
        self,
        *,
        conversation_id: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[ConversationRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if conversation_id is not None:
            clauses.append("conversation_id = ?")
            params.append(conversation_id)
        if org_id is not None:
            clauses.append("org_id = ?")
            params.append(org_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query(
            f"SELECT * FROM conversations {where} ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        )
        return [_row_to_conversation(r) for r in rows]

    def clear_conversation(self, conversation_id: str) -> None:
        with self._lock:
            self._db.execute(
                "DELETE FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            )

    # ------------------------------------------------------------------
    # Investigation memory
    # ------------------------------------------------------------------

    def add_investigation(self, record: InvestigationRecord) -> InvestigationRecord:
        with self._lock:
            self._db.insert(
                "investigations",
                {
                    "id": record.id,
                    "org_id": record.org_id,
                    "user_id": record.user_id,
                    "title": record.title,
                    "target": record.target,
                    "summary": record.summary,
                    "findings": dumps(record.findings),
                    "created_at": _iso(record.created_at),
                },
            )
        return record

    def list_investigations(
        self,
        *,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[InvestigationRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if org_id is not None:
            clauses.append("org_id = ?")
            params.append(org_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query(
            f"SELECT * FROM investigations {where} ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        )
        return [_row_to_investigation(r) for r in rows]

    # ------------------------------------------------------------------
    # Report history
    # ------------------------------------------------------------------

    def add_report(self, record: ReportRecord) -> ReportRecord:
        with self._lock:
            self._db.insert(
                "reports",
                {
                    "id": record.id,
                    "org_id": record.org_id,
                    "user_id": record.user_id,
                    "title": record.title,
                    "report_format": record.report_format,
                    "severity": record.severity,
                    "summary": record.summary,
                    "payload": dumps(record.payload),
                    "created_at": _iso(record.created_at),
                },
            )
        return record

    def list_reports(
        self,
        *,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[ReportRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if org_id is not None:
            clauses.append("org_id = ?")
            params.append(org_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query(
            f"SELECT * FROM reports {where} ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        )
        return [_row_to_report(r) for r in rows]

    # ------------------------------------------------------------------
    # User preferences
    # ------------------------------------------------------------------

    def set_preference(self, record: PreferenceRecord) -> PreferenceRecord:
        with self._lock:
            self._db.execute(
                """
                INSERT INTO preferences (id, org_id, user_id, user_key, value, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(org_id, user_id, user_key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (
                    record.id,
                    record.org_id,
                    record.user_id,
                    record.user_key,
                    record.value,
                    _iso(record.updated_at),
                ),
            )
        return record

    def get_preference(
        self,
        *,
        user_id: str,
        user_key: str,
        org_id: str | None = None,
    ) -> PreferenceRecord | None:
        row = self._db.query_one(
            """
            SELECT * FROM preferences
            WHERE org_id = ? AND user_id = ? AND user_key = ?
            """,
            (org_id or "", user_id, user_key),
        )
        return _row_to_preference(row) if row else None

    def list_preferences(
        self,
        *,
        user_id: str | None = None,
        org_id: str | None = None,
        limit: int = 50,
    ) -> list[PreferenceRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if org_id is not None:
            clauses.append("org_id = ?")
            params.append(org_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query(
            f"SELECT * FROM preferences {where} ORDER BY updated_at DESC LIMIT ?",
            (*params, limit),
        )
        return [_row_to_preference(r) for r in rows]

    # ------------------------------------------------------------------
    # Tool execution history
    # ------------------------------------------------------------------

    def add_tool_execution(self, record: ToolExecutionRecord) -> ToolExecutionRecord:
        with self._lock:
            self._db.insert(
                "tool_executions",
                {
                    "id": record.id,
                    "org_id": record.org_id,
                    "user_id": record.user_id,
                    "tool_name": record.tool_name,
                    "success": 1 if record.success else 0,
                    "input": dumps(record.input),
                    "output": dumps(record.output),
                    "error": record.error,
                    "created_at": _iso(record.created_at),
                },
            )
        return record

    def list_tool_executions(
        self,
        *,
        tool_name: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[ToolExecutionRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if tool_name is not None:
            clauses.append("tool_name = ?")
            params.append(tool_name)
        if org_id is not None:
            clauses.append("org_id = ?")
            params.append(org_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query(
            f"SELECT * FROM tool_executions {where} ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        )
        return [_row_to_tool_execution(r) for r in rows]

    # ------------------------------------------------------------------
    # Security findings history
    # ------------------------------------------------------------------

    def add_finding(self, record: FindingRecord) -> FindingRecord:
        with self._lock:
            self._db.insert(
                "findings",
                {
                    "id": record.id,
                    "org_id": record.org_id,
                    "user_id": record.user_id,
                    "finding_type": record.finding_type,
                    "target": record.target,
                    "severity": record.severity,
                    "description": record.description,
                    "detail": dumps(record.detail),
                    "created_at": _iso(record.created_at),
                },
            )
        return record

    def list_findings(
        self,
        *,
        finding_type: str | None = None,
        target: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[FindingRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if finding_type is not None:
            clauses.append("finding_type = ?")
            params.append(finding_type)
        if target is not None:
            clauses.append("target = ?")
            params.append(target)
        if org_id is not None:
            clauses.append("org_id = ?")
            params.append(org_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query(
            f"SELECT * FROM findings {where} ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        )
        return [_row_to_finding(r) for r in rows]

    def close(self) -> None:
        """Close the underlying database connection."""
        self._db.close()


# ---------------------------------------------------------------------------
# Row → record conversion helpers
# ---------------------------------------------------------------------------


def _row_to_conversation(row: Any) -> ConversationRecord:
    return ConversationRecord(
        id=row["id"],
        org_id=row["org_id"],
        user_id=row["user_id"],
        conversation_id=row["conversation_id"],
        role=row["role"],
        content=row["content"],
        metadata=loads(row["metadata"], {}),
        created_at=_parse_iso(row["created_at"]) or datetime.now(timezone.utc),
    )


def _row_to_investigation(row: Any) -> InvestigationRecord:
    return InvestigationRecord(
        id=row["id"],
        org_id=row["org_id"],
        user_id=row["user_id"],
        title=row["title"],
        target=row["target"],
        summary=row["summary"],
        findings=loads(row["findings"], []),
        created_at=_parse_iso(row["created_at"]) or datetime.now(timezone.utc),
    )


def _row_to_report(row: Any) -> ReportRecord:
    return ReportRecord(
        id=row["id"],
        org_id=row["org_id"],
        user_id=row["user_id"],
        title=row["title"],
        report_format=row["report_format"],
        severity=row["severity"],
        summary=row["summary"],
        payload=loads(row["payload"], {}),
        created_at=_parse_iso(row["created_at"]) or datetime.now(timezone.utc),
    )


def _row_to_preference(row: Any) -> PreferenceRecord:
    return PreferenceRecord(
        id=row["id"],
        org_id=row["org_id"],
        user_id=row["user_id"],
        user_key=row["user_key"],
        value=row["value"],
        updated_at=_parse_iso(row["updated_at"]) or datetime.now(timezone.utc),
    )


def _row_to_tool_execution(row: Any) -> ToolExecutionRecord:
    return ToolExecutionRecord(
        id=row["id"],
        org_id=row["org_id"],
        user_id=row["user_id"],
        tool_name=row["tool_name"],
        success=bool(row["success"]),
        input=loads(row["input"], {}),
        output=loads(row["output"], {}),
        error=row["error"],
        created_at=_parse_iso(row["created_at"]) or datetime.now(timezone.utc),
    )


def _row_to_finding(row: Any) -> FindingRecord:
    return FindingRecord(
        id=row["id"],
        org_id=row["org_id"],
        user_id=row["user_id"],
        finding_type=row["finding_type"],
        target=row["target"],
        severity=row["severity"],
        description=row["description"],
        detail=loads(row["detail"], {}),
        created_at=_parse_iso(row["created_at"]) or datetime.now(timezone.utc),
    )


__all__ = [
    "InMemoryMemoryRepository",
    "MemoryRepository",
    "SQLiteMemoryRepository",
]
