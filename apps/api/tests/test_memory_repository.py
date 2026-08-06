"""Tests for the Long-Term Memory repository layer (Phase 15A).

Covers both concrete backends:

- :class:`~app.memory.repository.InMemoryMemoryRepository`
- :class:`~app.memory.repository.SQLiteMemoryRepository`

Both implement the same :class:`~app.memory.repository.MemoryRepository`
interface, so the shared assertions run against each.
"""

from __future__ import annotations

import pytest

from app.db.db import MemoryDatabase
from app.memory.repository import (
    InMemoryMemoryRepository,
    MemoryRepository,
    SQLiteMemoryRepository,
)
from app.memory.schemas import (
    ConversationRecord,
    FindingRecord,
    InvestigationRecord,
    PreferenceRecord,
    ReportRecord,
    ToolExecutionRecord,
)


@pytest.fixture(
    params=[
        "memory",
        "sqlite",
    ]
)
def repo(request: pytest.FixtureRequest) -> MemoryRepository:
    """Parametrize tests over both repository implementations."""
    if request.param == "sqlite":
        return SQLiteMemoryRepository(db=MemoryDatabase(path=":memory:"))
    return InMemoryMemoryRepository()


def test_conversation_message_roundtrip(repo: MemoryRepository) -> None:
    """A recorded conversation message can be listed back."""
    record = ConversationRecord(
        conversation_id="conv-1",
        role="user",
        content="scan 8.8.8.8",
        org_id="org-1",
        user_id="user-1",
    )
    repo.add_conversation_message(record)

    items = repo.list_conversation_messages(conversation_id="conv-1")
    assert len(items) == 1
    assert items[0].content == "scan 8.8.8.8"
    assert items[0].conversation_id == "conv-1"


def test_conversation_filtering_by_scope(repo: MemoryRepository) -> None:
    """Conversation messages are isolated by org/user scoping."""
    repo.add_conversation_message(
        ConversationRecord(
            conversation_id="c",
            content="a",
            org_id="org-1",
            user_id="u-1",
        )
    )
    repo.add_conversation_message(
        ConversationRecord(
            conversation_id="c",
            content="b",
            org_id="org-2",
            user_id="u-2",
        )
    )

    assert len(repo.list_conversation_messages(org_id="org-1")) == 1
    assert len(repo.list_conversation_messages(user_id="u-2")) == 1
    assert len(repo.list_conversation_messages()) == 2


def test_clear_conversation(repo: MemoryRepository) -> None:
    """Clearing a conversation removes only its messages."""
    repo.add_conversation_message(
        ConversationRecord(conversation_id="c1", content="x")
    )
    repo.add_conversation_message(
        ConversationRecord(conversation_id="c2", content="y")
    )
    repo.clear_conversation("c1")
    assert len(repo.list_conversation_messages(conversation_id="c1")) == 0
    assert len(repo.list_conversation_messages(conversation_id="c2")) == 1


def test_investigation_roundtrip(repo: MemoryRepository) -> None:
    """An investigation can be recorded and listed."""
    record = InvestigationRecord(
        title="Investigate 8.8.8.8",
        target="8.8.8.8",
        summary="Found open ports.",
        findings=[{"port": 53}],
        org_id="org-1",
    )
    repo.add_investigation(record)

    items = repo.list_investigations(org_id="org-1")
    assert len(items) == 1
    assert items[0].title == "Investigate 8.8.8.8"
    assert items[0].findings == [{"port": 53}]


def test_report_newest_first(repo: MemoryRepository) -> None:
    """Reports are returned newest-first."""
    from datetime import datetime, timedelta, timezone

    base = datetime.now(timezone.utc)
    repo.add_report(
        ReportRecord(
            title="first",
            report_format="markdown",
            created_at=base - timedelta(seconds=10),
        )
    )
    repo.add_report(
        ReportRecord(
            title="second",
            report_format="json",
            created_at=base,
        )
    )

    items = repo.list_reports()
    assert [r.title for r in items] == ["second", "first"]


def test_preference_upsert(repo: MemoryRepository) -> None:
    """Setting the same key twice updates the value (upsert)."""
    repo.set_preference(
        PreferenceRecord(user_key="report_format", value="pdf", user_id="u1")
    )
    repo.set_preference(
        PreferenceRecord(user_key="report_format", value="json", user_id="u1")
    )

    saved = repo.get_preference(user_id="u1", user_key="report_format")
    assert saved is not None
    assert saved.value == "json"
    assert len(repo.list_preferences(user_id="u1")) == 1


def test_tool_execution_roundtrip(repo: MemoryRepository) -> None:
    """Tool executions can be recorded and filtered by name."""
    repo.add_tool_execution(
        ToolExecutionRecord(
            tool_name="nmap",
            success=True,
            input={"target": "8.8.8.8"},
            output={"hosts": []},
        )
    )
    repo.add_tool_execution(
        ToolExecutionRecord(tool_name="virustotal", success=False, error="timeout")
    )

    ok = repo.list_tool_executions(tool_name="nmap")
    assert len(ok) == 1
    assert ok[0].success is True
    assert ok[0].input == {"target": "8.8.8.8"}

    failed = repo.list_tool_executions(tool_name="virustotal")
    assert failed[0].success is False
    assert failed[0].error == "timeout"


def test_finding_filtering(repo: MemoryRepository) -> None:
    """Findings can be filtered by type and target."""
    repo.add_finding(
        FindingRecord(
            finding_type="malware",
            target="evil.com",
            severity="High",
            description="Known C2 domain.",
        )
    )
    repo.add_finding(
        FindingRecord(
            finding_type="vuln",
            target="db.internal",
            severity="Medium",
        )
    )

    assert len(repo.list_findings(finding_type="malware")) == 1
    assert len(repo.list_findings(target="evil.com")) == 1
    assert len(repo.list_findings()) == 2


def test_sqlite_persists_to_disk(tmp_path) -> None:
    """The SQLite backend writes to a real file and survives reopen."""
    db_path = str(tmp_path / "memory.db")
    db = MemoryDatabase(path=db_path)
    repo = SQLiteMemoryRepository(db=db)
    repo.add_report(ReportRecord(title="persisted", org_id="org-x"))
    repo.close()

    # Reopen the same file — data must be present.
    db2 = MemoryDatabase(path=db_path)
    repo2 = SQLiteMemoryRepository(db=db2)
    items = repo2.list_reports(org_id="org-x")
    assert len(items) == 1
    assert items[0].title == "persisted"
    repo2.close()


def test_schema_is_idempotent() -> None:
    """Opening the same database twice does not raise."""
    db = MemoryDatabase(path=":memory:")
    repo = SQLiteMemoryRepository(db=db)
    repo.add_report(ReportRecord(title="x"))
    # Re-init schema explicitly (as a fresh open would) — must not fail.
    db._init_schema()
    assert len(repo.list_reports()) == 1


def test_sqlite_connection_uses_expected_tables() -> None:
    """All six memory tables exist after init."""
    db = MemoryDatabase(path=":memory:")
    rows = db.query(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {row["name"] for row in rows}
    assert {
        "conversations",
        "investigations",
        "reports",
        "preferences",
        "tool_executions",
        "findings",
    }.issubset(names)
