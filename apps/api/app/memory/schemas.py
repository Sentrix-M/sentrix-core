"""Pydantic schemas for the Sentrix Long-Term Memory layer.

These records represent the six memory types persisted by
:class:`~app.memory.repository.MemoryRepository`. They are deliberately
framework-light Pydantic models so they can be used across the service, API,
and retriever layers without coupling to a specific storage backend.

The storage backend (SQLite today, PostgreSQL/SQLModel later) is hidden
behind the repository; these schemas are the stable public contract exposed
by :class:`~app.memory.service.MemoryService`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _now_utc() -> datetime:
    """Return the current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def _new_id() -> str:
    """Return a fresh UUID string."""
    return str(uuid.uuid4())


class MemoryRecord(BaseModel):
    """Base record shared by all memory types."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=_new_id, description="Stable record ID.")
    org_id: str = Field(default="", description="Tenant/organization scope.")
    user_id: str = Field(default="", description="Owning user scope.")
    created_at: datetime = Field(
        default_factory=_now_utc,
        description="When the record was recorded (UTC).",
    )


# ---------------------------------------------------------------------------
# Conversation Memory
# ---------------------------------------------------------------------------


class ConversationRecord(MemoryRecord):
    """A single message within a conversation."""

    conversation_id: str = Field(description="Client-generated conversation ID.")
    role: str = Field(default="user", description="user | assistant | system.")
    content: str = Field(default="", description="Message text.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible key-value metadata bag.",
    )


# ---------------------------------------------------------------------------
# Investigation Memory
# ---------------------------------------------------------------------------


class InvestigationRecord(MemoryRecord):
    """A security investigation."""

    title: str = Field(description="Investigation title.")
    target: str = Field(default="", description="Target indicator/host/domain.")
    summary: str = Field(default="", description="Narrative summary.")
    findings: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured findings from the investigation.",
    )


# ---------------------------------------------------------------------------
# Report History
# ---------------------------------------------------------------------------


class ReportRecord(MemoryRecord):
    """A generated incident report."""

    title: str = Field(description="Report title.")
    report_format: str = Field(default="markdown", description="markdown|json|pdf.")
    severity: str = Field(default="Medium", description="Overall severity.")
    summary: str = Field(default="", description="Executive summary.")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Serialized report payload.",
    )


# ---------------------------------------------------------------------------
# User Preferences
# ---------------------------------------------------------------------------


class PreferenceRecord(MemoryRecord):
    """A single user preference (key→value)."""

    user_key: str = Field(description="Preference key, e.g. 'report_format'.")
    value: str = Field(default="", description="Preference value.")
    updated_at: datetime = Field(
        default_factory=_now_utc,
        description="Last update time (UTC).",
    )


# ---------------------------------------------------------------------------
# Tool Execution History
# ---------------------------------------------------------------------------


class ToolExecutionRecord(MemoryRecord):
    """A single tool execution."""

    tool_name: str = Field(description="Name of the executed tool.")
    success: bool = Field(default=True, description="Whether execution succeeded.")
    input: dict[str, Any] = Field(default_factory=dict, description="Tool input.")
    output: dict[str, Any] = Field(default_factory=dict, description="Tool output.")
    error: str = Field(default="", description="Error message on failure.")


# ---------------------------------------------------------------------------
# Security Findings History
# ---------------------------------------------------------------------------


class FindingRecord(MemoryRecord):
    """A security finding."""

    finding_type: str = Field(description="e.g. 'malware', 'vuln', 'intel'.")
    target: str = Field(default="", description="Target indicator/host/domain.")
    severity: str = Field(default="Medium", description="Low|Medium|High|Critical.")
    description: str = Field(default="", description="Finding description.")
    detail: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured finding detail.",
    )


# ---------------------------------------------------------------------------
# List / response wrappers
# ---------------------------------------------------------------------------


class MemoryListResponse(BaseModel):
    """Generic list wrapper for memory query responses."""

    items: list[Any] = Field(default_factory=list)
    total: int = Field(default=0, description="Total number of items.")


__all__ = [
    "ConversationRecord",
    "FindingRecord",
    "InvestigationRecord",
    "MemoryListResponse",
    "MemoryRecord",
    "PreferenceRecord",
    "ReportRecord",
    "ToolExecutionRecord",
]
