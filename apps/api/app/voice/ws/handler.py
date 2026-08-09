"""Voice WebSocket handler — accumulate audio, transcribe once, route to chat.

This module contains the core loop for a single voice WebSocket connection:

1. Authenticate the client (JWT).
2. Accumulate incoming audio chunks (``audio`` binary frames) into the
   :class:`VoiceConnection` buffer while the :class:`VoiceActivityDetector`
   tracks speech.
3. When end-of-speech is detected (via VAD silence or an explicit ``end``
   control message), run the STT provider a *single* time over the buffered
   utterance.
4. Emit a ``transcript`` event, then feed the transcript into the existing
   conversation pipeline exactly like the text chat would, and emit a
   ``response`` event with the reply.

The handler deliberately reuses the existing conversation pipeline through
``build_kernel_pipeline`` — it does not re-implement routing, planning, tool
execution, memory, or reports. It is a thin transport over the text chat.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketException

from app.kernel.integration import build_kernel_pipeline
from app.schemas.conversation import ConversationMessageRequest
from app.services.conversation_service import ConversationService
from app.voice.schemas import (
    VoiceClientEvent,
    VoiceEventType,
    VoiceServerEvent,
)
from app.voice.stt.base import SpeechToTextProvider
from app.voice.stt.factory import create_stt_provider
from app.voice.ws.auth import authenticate_websocket
from app.voice.ws.connection import VoiceConnection

logger = logging.getLogger(__name__)


class VoiceConnectionHandler:
    """Handles a single authenticated voice WebSocket session.

    :param websocket: The active WebSocket.
    :param stt_provider: Optional STT provider. Defaults to
        :func:`~app.voice.stt.factory.create_stt_provider` (mock by default).
    :param conversation_service: Optional conversation service. When omitted,
        a :class:`ConversationService` backed by a kernel pipeline built from
        :func:`~app.kernel.integration.build_kernel_pipeline` is created.
    """

    def __init__(
        self,
        websocket: WebSocket,
        *,
        stt_provider: SpeechToTextProvider | None = None,
        conversation_service: ConversationService | None = None,
    ) -> None:
        self._websocket = websocket
        self._stt_provider = stt_provider or create_stt_provider()
        self._conversation_service = conversation_service or self._build_service()
        self._connection = VoiceConnection(stt_provider=self._stt_provider)

    def _build_service(self) -> ConversationService:
        """Build a conversation service wired with the default kernel pipeline."""
        pipeline = build_kernel_pipeline()
        return ConversationService(pipeline=pipeline)

    @classmethod
    def from_app_state(
        cls,
        websocket: WebSocket,
        *,
        stt_provider: SpeechToTextProvider | None = None,
    ) -> VoiceConnectionHandler:
        """Build a handler reusing the shared app-state services.

        Mirrors the wiring used by the streaming endpoint: the shared
        ``tool_executor``, ``memory_service``, and ``report_service`` from
        ``app.state`` are composed into a kernel pipeline, so a voice
        transcript routes through the same Planner → ToolCoordinator →
        Executor → Provider flow as text chat.
        """
        state = websocket.app.state
        tool_executor = getattr(state, "tool_executor", None)
        memory_service = getattr(state, "memory_service", None)
        report_service = getattr(state, "report_service", None)

        pipeline = build_kernel_pipeline(
            tool_executor=tool_executor,
            memory_service=memory_service,
            report_service=report_service,
        )
        return cls(
            websocket,
            stt_provider=stt_provider,
            conversation_service=ConversationService(
                memory_service=memory_service,
                pipeline=pipeline,
            ),
        )

    async def _send(self, event: VoiceServerEvent) -> None:
        """Send a JSON-encoded server event to the client."""
        await self._websocket.send_text(json.dumps(event.to_dict()))

    async def _transcribe_and_respond(self) -> None:
        """Run one transcription and route the text into the chat pipeline."""
        audio = self._connection.audio_buffer
        self._connection.reset_utterance()

        if not audio:
            await self._send(
                VoiceServerEvent(
                    type=VoiceEventType.ERROR,
                    detail="No audio received for this utterance.",
                )
            )
            return

        try:
            result = await self._stt_provider.transcribe(audio)
        except Exception as exc:  # noqa: BLE001 - surface as a non-fatal error
            logger.exception("STT transcription failed.")
            await self._send(
                VoiceServerEvent(
                    type=VoiceEventType.ERROR,
                    detail=f"Transcription failed: {exc}",
                )
            )
            return

        transcript = result.text.strip()
        if not transcript:
            await self._send(
                VoiceServerEvent(
                    type=VoiceEventType.ERROR,
                    detail="No speech was recognised.",
                )
            )
            return

        # Emit the final transcript.
        await self._send(
            VoiceServerEvent(
                type=VoiceEventType.TRANSCRIPT,
                text=transcript,
                extra={"final": True},
            )
        )

        # Route into the existing conversation pipeline (same as text chat).
        conversation_id = self._connection.conversation_id or "voice-default"
        request = ConversationMessageRequest(
            conversation_id=conversation_id,
            message=transcript,
        )
        try:
            response = self._conversation_service.reply(request)
        except Exception as exc:  # noqa: BLE001 - reply must not break the socket
            logger.exception("Conversation reply failed for voice transcript.")
            await self._send(
                VoiceServerEvent(
                    type=VoiceEventType.ERROR,
                    detail=f"Reply failed: {exc}",
                )
            )
            return

        await self._send(
            VoiceServerEvent(
                type=VoiceEventType.RESPONSE,
                text=response.response,
                conversation_id=conversation_id,
            )
        )
        await self._send(
            VoiceServerEvent(
                type=VoiceEventType.DONE,
                conversation_id=conversation_id,
            )
        )

    async def handle(self) -> None:
        """Run the voice WebSocket message loop."""
        await self._websocket.accept()
        await self._stt_provider.load()
        await self._send(
            VoiceServerEvent(
                type=VoiceEventType.STATUS,
                text="connected",
                detail="Voice session ready. Send audio frames, then 'end'.",
            )
        )

        try:
            while True:
                message = await self._websocket.receive()

                if message.get("type") == "websocket.disconnect":
                    break

                if message.get("type") == "websocket.receive":
                    data = message.get("text") or message.get("bytes")
                    await self._on_data(data)
                    continue

                # Treat unknown message types as a disconnect.
                break
        except WebSocketException:
            raise
        except Exception:  # noqa: BLE001 - log and close on unexpected errors
            logger.exception("Voice WebSocket handler error.")
        finally:
            await self._stt_provider.close()

    async def _on_data(self, data: Any) -> None:
        """Handle a single binary or text frame from the client."""
        if isinstance(data, bytes):
            # Binary audio frame.
            self._connection.add_audio(data)
            # If VAD detects end-of-speech, transcribe once.
            if self._connection.vad.should_finalize():
                await self._transcribe_and_respond()
            return

        if isinstance(data, str):
            try:
                event = VoiceClientEvent(**json.loads(data))
            except Exception:  # noqa: BLE001 - ignore malformed control messages
                return

            if event.type == VoiceEventType.CONFIG and event.conversation_id:
                self._connection.conversation_id = event.conversation_id
                await self._send(
                    VoiceServerEvent(
                        type=VoiceEventType.STATUS,
                        text="configured",
                        conversation_id=self._connection.conversation_id,
                    )
                )
            elif event.type == VoiceEventType.END:
                await self._transcribe_and_respond()
            return

        # Unknown frame type — ignore.


async def handle_voice_connection(websocket: WebSocket) -> None:
    """Entrypoint for the FastAPI WebSocket route.

    Authenticates the client, then delegates to :class:`VoiceConnectionHandler`.
    """
    try:
        await authenticate_websocket(websocket)
    except WebSocketException:
        # FastAPI will convert the exception to a close frame.
        raise

    handler = VoiceConnectionHandler.from_app_state(websocket)
    await handler.handle()


__all__ = ["VoiceConnectionHandler", "handle_voice_connection"]
