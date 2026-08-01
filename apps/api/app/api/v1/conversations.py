"""Conversation routes under ``/api/v1/conversations``.

Exposes the AI conversation use cases implemented by
:class:`ConversationService`. The endpoint accepts a user message scoped to a
client-generated ``conversation_id`` and returns a mock assistant reply with a
future-proof metadata block reserved for reasoning/evidence/sources/tools.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_conversation_service
from app.schemas.conversation import (
    ConversationMessageRequest,
    ConversationMessageResponse,
)
from app.services.conversation_service import ConversationService
from app.streaming.manager import StreamingManager

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post(
    "/message",
    response_model=ConversationMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message to the AI conversation engine",
)
async def send_message(
    payload: ConversationMessageRequest,
    conversation_service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> ConversationMessageResponse:
    """Send a user message and receive an assistant response.

    ``conversation_id`` is client-generated; no server-side state is stored.
    The ``metadata`` block is reserved for reasoning, evidence, sources, and
    tools once the AI router and RAG layers are integrated.
    """
    return conversation_service.reply(payload)


@router.post(
    "/stream",
    response_class=StreamingResponse,
    summary="Stream an AI response via Server-Sent Events",
)
async def stream_message(
    payload: ConversationMessageRequest,
) -> StreamingResponse:
    """Stream the assistant reply as Server-Sent Events.

    The original ``/message`` REST endpoint is unchanged. The response is
    ``text/event-stream`` and emits ``status`` (thinking / generating),
    ``token``, ``completed``, ``error``, and ``done`` events using the
    :class:`StreamingManager` over the kernel pipeline (offline mock provider).
    """
    manager = StreamingManager()
    return StreamingResponse(
        manager.stream(payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
