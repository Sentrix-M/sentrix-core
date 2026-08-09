"""Tests for the Long-Term Memory service layer (Phase 15A).

Covers the :class:`~app.memory.service.MemoryService`, including the
:class:`~app.memory.models.MemoryItem`-based store protocols that let it
serve as a drop-in for :class:`~app.memory.manager.MemoryManager`.
"""

from __future__ import annotations

import pytest

from app.memory.models import MemoryItem
from app.memory.service import MemoryService


@pytest.fixture
def service() -> MemoryService:
    """A fresh in-memory-backed service for each test."""
    return MemoryService()


def test_record_and_get_conversation_messages(service: MemoryService) -> None:
    """Conversation messages are recorded and retrieved scoped."""
    service.record_conversation_message(
        conversation_id="conv-1",
        content="scan 8.8.8.8",
        role="user",
        org_id="org-1",
        user_id="user-1",
    )
    service.record_conversation_message(
        conversation_id="conv-1",
        content="Found open ports.",
        role="assistant",
        org_id="org-1",
        user_id="user-1",
    )

    messages = service.get_conversation_messages(conversation_id="conv-1")
    assert len(messages) == 2
    contents = {m.content for m in messages}
    assert contents == {"scan 8.8.8.8", "Found open ports."}

    # Scoped query.
    assert len(service.get_conversation_messages(user_id="user-1")) == 2
    assert len(service.get_conversation_messages(user_id="other")) == 0


def test_clear_conversation(service: MemoryService) -> None:
    """Clearing a conversation removes only its messages."""
    service.record_conversation_message(conversation_id="c1", content="a")
    service.record_conversation_message(conversation_id="c2", content="b")

    service.clear_conversation("c1")
    assert len(service.get_conversation_messages(conversation_id="c1")) == 0
    assert len(service.get_conversation_messages(conversation_id="c2")) == 1


def test_record_and_get_investigations(service: MemoryService) -> None:
    """Investigations are recorded with structured findings."""
    service.record_investigation(
        title="Investigate 8.8.8.8",
        target="8.8.8.8",
        summary="Found exposed services.",
        findings=[{"port": 53, "state": "open"}],
        org_id="org-1",
    )

    items = service.get_investigations(org_id="org-1")
    assert len(items) == 1
    assert items[0].findings == [{"port": 53, "state": "open"}]


def test_record_and_get_reports(service: MemoryService) -> None:
    """Report history is recorded with payload and severity."""
    service.record_report(
        title="Weekly Threat Report",
        report_format="json",
        severity="High",
        summary="Three critical findings.",
        payload={"incidents": 3},
    )

    reports = service.get_reports()
    assert len(reports) == 1
    assert reports[0].severity == "High"
    assert reports[0].payload == {"incidents": 3}


def test_preference_upsert(service: MemoryService) -> None:
    """Setting a preference twice updates the value."""
    service.set_preference(user_key="report_format", value="pdf", user_id="u1")
    service.set_preference(user_key="report_format", value="json", user_id="u1")

    saved = service.get_preference(user_key="report_format", user_id="u1")
    assert saved is not None
    assert saved.value == "json"
    assert len(service.get_preferences(user_id="u1")) == 1


def test_record_and_get_tool_executions(service: MemoryService) -> None:
    """Tool execution history is recorded and filtered by tool."""
    service.record_tool_execution(
        tool_name="nmap",
        success=True,
        input={"target": "8.8.8.8"},
        output={"hosts": [{"ip": "8.8.8.8"}]},
    )
    service.record_tool_execution(
        tool_name="virustotal",
        success=False,
        error="rate limited",
    )

    nmap_runs = service.get_tool_executions(tool_name="nmap")
    assert len(nmap_runs) == 1
    assert nmap_runs[0].output == {"hosts": [{"ip": "8.8.8.8"}]}

    failures = service.get_tool_executions(tool_name="virustotal")
    assert failures[0].success is False
    assert failures[0].error == "rate limited"


def test_record_and_get_findings(service: MemoryService) -> None:
    """Security findings are recorded and filterable."""
    service.record_finding(
        finding_type="malware",
        target="evil.com",
        severity="Critical",
        description="Command-and-control domain.",
        detail={"source": "virustotal"},
    )

    findings = service.get_findings(finding_type="malware")
    assert len(findings) == 1
    assert findings[0].severity == "Critical"
    assert findings[0].target == "evil.com"


def test_store_protocol_append_and_get_history(service: MemoryService) -> None:
    """MemoryService implements the ConversationStore protocol."""
    service.append(
        "conv-1",
        MemoryItem(content="what is 8.8.8.8?", role="user"),
    )
    service.append(
        "conv-1",
        MemoryItem(content="It is a public DNS resolver.", role="assistant"),
    )

    history = service.get_history("conv-1")
    assert history.conversation_id == "conv-1"
    contents = {i.content for i in history.history}
    assert contents == {"what is 8.8.8.8?", "It is a public DNS resolver."}


def test_project_store_protocol(service: MemoryService) -> None:
    """MemoryService implements the ProjectStore read/write protocol."""
    service.set_context("proj-1", "industry", "finance")
    service.set_context("proj-1", "region", "eu")

    project = service.get("proj-1")
    assert project.project_id == "proj-1"
    assert project.context["industry"] == "finance"
    assert project.context["region"] == "eu"


def test_clear_with_conversation_id(service: MemoryService) -> None:
    """service.clear removes only the named conversation."""
    service.append("conv-1", MemoryItem(content="a", role="user"))
    service.append("conv-2", MemoryItem(content="b", role="user"))

    service.clear("conv-1")
    assert len(service.get_conversation_messages(conversation_id="conv-1")) == 0
    assert len(service.get_conversation_messages(conversation_id="conv-2")) == 1
