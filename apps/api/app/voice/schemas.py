"""Pydantic models for the Sentrix Voice Assistant WebSocket transport.

The voice endpoint uses a small JSON message contract over the WebSocket:

Client → server
---------------
- ``config`` — sets the ``conversation_id`` for the utterance.
- ``end`` — signals end-of-speech / end of the utterance so the server runs a
  single transcription and feeds the result into the conversation pipeline.

Server → client
---------------
- ``status`` — connection / phase markers.
- ``transcript`` — partial or final transcript text.
- ``response`` — the text reply from the existing conversation pipeline.
- ``done`` — terminal event for the utterance.
- ``error`` — a non-fatal error that closes the utterance cleanly.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TextToSpeechRequest(BaseModel):
    """Input for the text-to-speech synthesis endpoint.

    ``text`` is the completed assistant message to speak. ``voice`` is an
    optional provider-specific voice identifier (e.g. ``af_default`` for
    Kokoro); when omitted the provider uses its default voice.
    """

    text: str = Field(..., min_length=1, max_length=8000)
    #: Optional provider-specific voice identifier.
    voice: str | None = Field(default=None, max_length=64)


class VoiceEventType(str, Enum):
    """Event names exchanged over the voice WebSocket."""

    # Client → server
    CONFIG = "config"
    END = "end"

    # Server → client
    STATUS = "status"
    TRANSCRIPT = "transcript"
    RESPONSE = "response"
    DONE = "done"
    ERROR = "error"


class VoiceClientEvent(BaseModel):
    """A message sent from the client to the voice server."""

    type: VoiceEventType
    conversation_id: str | None = Field(default=None, max_length=128)
    #: Transcript kind for `transcript` events: "partial" or "final".
    kind: str | None = Field(default=None, max_length=16)


class VoiceServerEvent(BaseModel):
    """A message sent from the voice server to the client."""

    type: VoiceEventType
    #: Payload varies by event type (e.g. status name, transcript text).
    text: str | None = None
    detail: str | None = None
    conversation_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the event for the WebSocket JSON payload."""
        payload: dict[str, Any] = {"type": self.type.value}
        if self.text is not None:
            payload["text"] = self.text
        if self.detail is not None:
            payload["detail"] = self.detail
        if self.conversation_id is not None:
            payload["conversation_id"] = self.conversation_id
        if self.extra:
            payload.update(self.extra)
        return payload


class VoiceEvent(BaseModel):
    """Union-ish wrapper kept for type clarity / future expansion."""

    type: VoiceEventType
    data: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "TextToSpeechRequest",
    "VoiceClientEvent",
    "VoiceEvent",
    "VoiceEventType",
    "VoiceServerEvent",
]
