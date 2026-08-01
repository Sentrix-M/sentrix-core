"""Unit and integration tests for the Streaming Response Layer.

Covers the SSE event builders, wire-format serialisation, the
:class:`StreamingManager` orchestrator, and the HTTP endpoint
``POST /api/v1/conversations/stream``.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.conversation import ConversationMessageRequest
from app.streaming.events import (
    completed_event,
    done_event,
    error_event,
    status_event,
    token_event,
)
from app.streaming.formatter import format_event
from app.streaming.manager import StreamingManager


def _valid_payload() -> dict[str, str]:
    return {
        "conversation_id": f"conv-{uuid.uuid4().hex[:8]}",
        "message": "Investigate the beacon pattern on LAB-07",
    }


def _parse_block(block: str) -> tuple[str, dict[str, Any]]:
    """Parse one SSE block into ``(event, payload)``."""
    event = ""
    data = ""
    for line in block.strip().splitlines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data = line.split(":", 1)[1].strip()
    return event, json.loads(data) if data else {}


async def _collect(stream: Any) -> list[str]:
    """Drain an async generator into a list of blocks."""
    return [block async for block in stream]


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a TestClient with the application lifespan executed."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Event builders
# ---------------------------------------------------------------------------


def test_status_event_builds_payload() -> None:
    event = status_event("thinking", detail="preparing")
    assert event.event == "status"
    assert event.data["status"] == "thinking"
    assert event.data["detail"] == "preparing"
    assert event.data["at"]


def test_token_event_builds_payload() -> None:
    event = token_event("correlated")
    assert event.event == "token"
    assert event.data == {"token": "correlated"}


def test_completed_event_builds_payload() -> None:
    event = completed_event(
        provider="mock",
        model="sentrix-mock-0.1",
        content="done",
        execution_time_ms=12,
    )
    assert event.event == "completed"
    assert event.data["provider"] == "mock"
    assert event.data["model"] == "sentrix-mock-0.1"
    assert event.data["content"] == "done"
    assert event.data["execution_time_ms"] == 12


def test_error_and_done_events() -> None:
    assert error_event("boom").event == "error"
    assert done_event().event == "done"


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


def test_format_event_produces_sse_block() -> None:
    block = format_event(token_event("hello"))
    lines = block.split("\n")
    assert lines[0] == "event: token"
    assert lines[1].startswith("data: ")
    assert block.endswith("\n\n")
    _, payload = _parse_block(block)
    assert payload == {"token": "hello"}


# ---------------------------------------------------------------------------
# StreamingManager
# ---------------------------------------------------------------------------


def test_manager_emits_full_event_sequence() -> None:
    manager = StreamingManager(token_delay_seconds=0)
    request = ConversationMessageRequest(**_valid_payload())
    blocks = asyncio.run(_collect(manager.stream(request)))

    assert blocks, "Expected at least one SSE block."
    assert blocks[0].startswith(": connected")

    events = [_parse_block(b)[0] for b in blocks]
    assert events[0] == ""  # heartbeat comment has no event name
    assert events.count("status") == 2  # thinking + generating
    assert "token" in events
    assert "completed" in events
    assert events[-1] == "done"

    # Reassembled tokens must equal the completed content.
    tokens: list[str] = []
    content = ""
    for block in blocks:
        event, payload = _parse_block(block)
        if event == "token":
            tokens.append(str(payload["token"]))
        elif event == "completed":
            content = str(payload["content"])
    assert " ".join(tokens) == content


class _BrokenPipeline:
    """Minimal duck-typed pipeline whose ``run`` always raises."""

    def run(self, **kwargs: object) -> Any:  # noqa: ARG002 - test double signature
        raise RuntimeError("provider exploded")


def test_manager_wraps_errors_before_done() -> None:
    manager = StreamingManager(pipeline=_BrokenPipeline(), token_delay_seconds=0)  # type: ignore[arg-type]
    request = ConversationMessageRequest(**_valid_payload())
    blocks = asyncio.run(_collect(manager.stream(request)))

    events = [_parse_block(b)[0] for b in blocks]
    assert "error" in events
    assert events[-1] == "done"


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------


def test_stream_endpoint_returns_sse_stream(client: TestClient) -> None:
    payload = _valid_payload()
    response = client.post("/api/v1/conversations/stream", json=payload)

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    blocks = [b for b in response.text.split("\n\n") if b.strip()]
    events = [_parse_block(b)[0] for b in blocks]
    assert events[0] == ""  # heartbeat comment
    assert "status" in events
    assert "token" in events
    assert "completed" in events
    assert events[-1] == "done"


def test_stream_endpoint_reassembled_content_matches_completed(
    client: TestClient,
) -> None:
    payload = _valid_payload()
    response = client.post("/api/v1/conversations/stream", json=payload)
    assert response.status_code == 200

    tokens: list[str] = []
    content = ""
    for block in response.text.split("\n\n"):
        event, data = _parse_block(block)
        if event == "token":
            tokens.append(str(data["token"]))
        elif event == "completed":
            content = str(data["content"])
    assert " ".join(tokens) == content


def test_stream_endpoint_validates_payload(client: TestClient) -> None:
    payload = _valid_payload()
    payload["message"] = ""
    response = client.post("/api/v1/conversations/stream", json=payload)
    assert response.status_code == 422
