"""Conversation routes under ``/api/v1/conversations``.

Exposes the AI conversation use cases implemented by
:class:`ConversationService`. The endpoint accepts a user message scoped to a
client-generated ``conversation_id`` and returns a mock assistant reply with a
future-proof metadata block reserved for reasoning/evidence/sources/tools.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    get_conversation_service,
    get_current_user,
    get_tool_executor,
)
from app.models.user import User
from app.schemas.conversation import (
    ConversationMessageRequest,
    ConversationMessageResponse,
)
from app.services.conversation_service import ConversationService
from app.streaming.manager import StreamingManager
from app.tools.executor import ToolExecutor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post(
    "/message",
    response_model=ConversationMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message to the AI conversation engine",
)
async def send_message(
    payload: ConversationMessageRequest,
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001 - auth guard
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
    current_user: Annotated[User, Depends(get_current_user)],
    tool_executor: Annotated[ToolExecutor, Depends(get_tool_executor)],
) -> StreamingResponse:
    """Stream the assistant reply as Server-Sent Events.

    The original ``/message`` REST endpoint is unchanged. The response is
    ``text/event-stream`` and emits ``status`` (thinking / generating),
    ``token``, ``completed``, ``error``, and ``done`` events using the
    :class:`StreamingManager` over the kernel pipeline (offline mock provider).

    The streaming pipeline is wired with the shared mock Tool Engine so user
    messages that express a tool intent (e.g. "list uploaded documents",
    "run python", "execute terminal command") trigger the corresponding mock
    tool and its output is fed into the prompt for a natural explanation.
    """
    manager = StreamingManager(tool_executor=tool_executor)
    # Diagnostic: surface the provider instance wired into this stream's
    # kernel pipeline so operators can confirm Gemini (or the mock fallback)
    # is actually being used per request.
    pipeline = manager._pipeline  # noqa: SLF001 - diagnostic access
    provider_names = pipeline.registry.names()
    provider = (
        pipeline.registry.get(provider_names[0]) if provider_names else None
    )
    logger.info(
        "conversations.stream_message — kernel pipeline provider: name=%s  type=%s",
        getattr(provider, "name", "?"),
        type(provider).__name__ if provider is not None else "None",
    )
    return StreamingResponse(
        manager.stream(
            payload,
            user_permissions=set(current_user.permissions),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
