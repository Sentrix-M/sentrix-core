"""Text-to-Speech routes under ``/api/v1/tts``.

Exposes a single authenticated HTTP endpoint that converts a completed
assistant message into audio bytes. The endpoint is provider-agnostic: it
builds a :class:`~app.voice.tts.base.TextToSpeechProvider` via
:func:`~app.voice.tts.factory.create_tts_provider` and returns the synthesised
audio directly. The frontend always calls this endpoint (never a provider
directly), so Mock/Kokoro/OpenAI/ElevenLabs/Piper all live behind one API.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.api.deps import get_current_user
from app.voice.schemas import TextToSpeechRequest
from app.voice.tts.base import TextToSpeechProvider
from app.voice.tts.factory import create_tts_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts", tags=["tts"])


def _build_provider() -> TextToSpeechProvider:
    """Construct the configured TTS provider for this request."""
    return create_tts_provider()


@router.post(
    "/synthesize",
    summary="Synthesize speech from text",
    response_class=Response,
)
async def synthesize(
    payload: TextToSpeechRequest,
    _user: Annotated[object, Depends(get_current_user)],
) -> Response:
    """Convert ``payload.text`` into audio bytes.

    The endpoint is auth-protected and returns the raw audio (e.g.
    ``audio/wav``) so the browser can play it directly. The selected provider
    is resolved per request from configuration (defaults to the mock).
    """
    provider = _build_provider()
    try:
        await provider.load()
        result = await provider.synthesize(payload.text)
    except Exception as exc:  # noqa: BLE001 - surface as a clean 500
        logger.exception("TTS synthesis failed.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech synthesis failed: {exc}",
        ) from exc
    finally:
        await provider.close()

    return Response(
        content=result.audio,
        media_type=result.media_type,
        headers={
            "X-TTS-Provider": result.provider,
            "Cache-Control": "no-store",
        },
    )


__all__ = ["router"]
