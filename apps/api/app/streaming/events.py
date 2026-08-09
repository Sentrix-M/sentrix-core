"""SSE event definitions for the Sentrix Streaming Response Layer.

Each event is a small immutable :class:`StreamEvent` carrying an event name
and a JSON-serialisable payload. The factory helpers below are the single
source of truth for the wire contract used by the streaming endpoint:

- ``status`` — thinking / generating phase markers
- ``token`` — one partial-response chunk
- ``completed`` — terminal metadata + full assembled reply
- ``error`` — a non-fatal error that closes the stream cleanly
- ``done`` — always the final event
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class StreamEvent:
    """A single Server-Sent Event."""

    event: str
    data: dict[str, Any] = field(default_factory=dict)


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def status_event(status: str, *, detail: str | None = None) -> StreamEvent:
    """Build a ``status`` event (``thinking`` / ``generating``)."""
    payload: dict[str, Any] = {"status": status, "at": _now()}
    if detail is not None:
        payload["detail"] = detail
    return StreamEvent("status", payload)


def token_event(token: str) -> StreamEvent:
    """Build a ``token`` event carrying one partial-response chunk."""
    return StreamEvent("token", {"token": token})


def completed_event(
    *,
    provider: str,
    model: str | None,
    content: str,
    execution_time_ms: int,
    citations: list[dict[str, object]] | None = None,
    tools_used: list[str] | None = None,
) -> StreamEvent:
    """Build a ``completed`` event with the full assembled reply."""
    payload: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "content": content,
        "execution_time_ms": execution_time_ms,
        "at": _now(),
    }
    if citations:
        payload["citations"] = citations
    if tools_used:
        payload["tools_used"] = tools_used
    return StreamEvent("completed", payload)


def error_event(message: str) -> StreamEvent:
    """Build an ``error`` event closing the stream cleanly."""
    return StreamEvent("error", {"message": message, "at": _now()})


def done_event() -> StreamEvent:
    """Build the terminal ``done`` event."""
    return StreamEvent("done", {})


__all__ = [
    "StreamEvent",
    "completed_event",
    "done_event",
    "error_event",
    "status_event",
    "token_event",
]
