"""Pydantic schemas for the conversation module.

The response envelope is deliberately "future-proof": it carries a metadata
block whose fields (reasoning, evidence, sources, tools) are reserved for the
real AI engine (routing, RAG, tool execution) and are ``None`` in the current
mock implementation. Clients can render these sections without schema churn.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ConversationMessageRequest(BaseModel):
    """Payload for sending a single message within a conversation."""

    conversation_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)


class ConversationMetadata(BaseModel):
    """Optional assistant-response metadata.

    Reserved capabilities for the AI engine. All fields are optional so the
    mock response and older clients remain compatible as capabilities are
    populated incrementally.
    """

    model: str | None = None
    reasoning: list[str] | None = None
    evidence: list[str] | None = None
    sources: list[str] | None = None
    tools_used: list[str] | None = None
    execution_time_ms: int | None = None


class ConversationMessageResponse(BaseModel):
    """Response envelope for a single conversation turn."""

    conversation_id: str
    response: str
    timestamp: datetime
    metadata: ConversationMetadata = Field(default_factory=ConversationMetadata)

