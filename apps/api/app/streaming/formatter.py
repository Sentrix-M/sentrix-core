"""Serialise :class:`StreamEvent` objects into Server-Sent Event (SSE) blocks.

The wire format follows the SSE spec::

    event: <name>
    data: <json-payload>
    <blank line>

A ``: <comment>`` block is used as a connection heartbeat so browsers and
proxies see an immediate byte from the server.
"""

from __future__ import annotations

import json

from app.streaming.events import StreamEvent


def format_event(event: StreamEvent) -> str:
    """Render one :class:`StreamEvent` as an SSE block.

    :return: The complete block, including the terminating blank line.
    """
    payload = json.dumps(event.data, separators=(",", ":"), ensure_ascii=True)
    return f"event: {event.event}\ndata: {payload}\n\n"


def heartbeat() -> str:
    """Return an SSE comment used to open a stream immediately."""
    return ": connected\n\n"


__all__ = ["format_event", "heartbeat"]
