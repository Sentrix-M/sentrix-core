"""Voice routes under ``/api/v1/voice``.

Exposes the real-time voice WebSocket endpoint for the Sentrix Voice
Assistant. The endpoint authenticates the client, then delegates to the
:class:`~app.voice.ws.handler.VoiceConnectionHandler` which accumulates audio,
runs a single transcription per utterance, and routes the transcript into the
existing conversation pipeline (planner → tool coordinator → executor →
provider). No new architecture is introduced here — it is a thin transport
over the existing text chat flow.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from app.voice.ws.handler import handle_voice_connection

router = APIRouter(prefix="/voice", tags=["voice"])


@router.websocket("/transcribe")
async def transcribe(websocket: WebSocket) -> None:
    """Transcribe a spoken utterance and reply via the AI pipeline.

    The client authenticates with a JWT via ``?token=`` or the
    ``Authorization`` header, streams raw audio frames, optionally sends a
    ``config`` event to set the conversation id, and sends ``end`` (or relies
    on VAD end-of-speech) to trigger a single transcription. The server emits
    ``status``, ``transcript``, ``response``, and ``done`` events.
    """
    await handle_voice_connection(websocket)


__all__ = ["router"]
