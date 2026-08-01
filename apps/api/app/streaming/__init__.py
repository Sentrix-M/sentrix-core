"""Sentrix Streaming Response Layer.

Server-Sent Events (SSE) support for the kernel pipeline:

- :mod:`events` — typed, immutable event definitions and builders
- :mod:`formatter` — SSE wire-format serialisation
- :mod:`manager` — orchestrates a conversation turn into a live stream

The streaming endpoint is exposed at ``POST /api/v1/conversations/stream``
while the original REST endpoint (``/message``) is left unchanged.
"""

from app.streaming.events import (
    StreamEvent,
    completed_event,
    done_event,
    error_event,
    status_event,
    token_event,
)
from app.streaming.formatter import format_event, heartbeat
from app.streaming.manager import DEFAULT_TOKEN_DELAY_SECONDS, StreamingManager

__all__ = [
    "DEFAULT_TOKEN_DELAY_SECONDS",
    "StreamEvent",
    "StreamingManager",
    "completed_event",
    "done_event",
    "error_event",
    "format_event",
    "heartbeat",
    "status_event",
    "token_event",
]
