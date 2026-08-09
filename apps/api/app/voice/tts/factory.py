"""Text-to-Speech provider factory for the Sentrix Voice Assistant.

:func:`create_tts_provider` builds a TTS backend by name, mirroring the
existing :func:`~app.voice.stt.factory.create_stt_provider` pattern. The
default is the offline, deterministic :class:`MockTtsProvider` so the voice
output layer works on any machine with no heavy model. Kokoro is only
constructed when explicitly requested via ``TTS_PROVIDER`` — it is never
forced on developer machines.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.voice.tts.base import TextToSpeechProvider
from app.voice.tts.mock import MockTtsProvider

logger = logging.getLogger(__name__)

#: Provider name used when no explicit TTS provider is requested.
DEFAULT_TTS_PROVIDER = "mock"


class TtsConstructor(Protocol):
    """Callable that builds a :class:`TextToSpeechProvider` instance."""

    def __call__(self) -> TextToSpeechProvider:
        """Return a configured TTS provider instance."""
        ...


def _build_kokoro() -> TextToSpeechProvider:
    """Construct a :class:`~app.voice.tts.kokoro.KokoroTTSProvider`.

    The import is deferred so ``kokoro`` (and its heavy dependencies) are only
    required when this provider is actually selected. If the package (or
    model) is unavailable, the constructor raises and the factory degrades to
    the mock.
    """
    from app.voice.tts.kokoro import KokoroTTSProvider

    return KokoroTTSProvider()


def create_tts_provider(name: str | None = None) -> TextToSpeechProvider:
    """Return a configured TTS provider instance.

    :param name: Provider name. Defaults to the ``TTS_PROVIDER`` setting or
        :data:`DEFAULT_TTS_PROVIDER`.
    :raises KeyError: When ``name`` is not a registered provider and no
        fallback is available.
    """
    provider_name = name or _resolve_default()
    logger.info("create_tts_provider() — requested provider: %s", provider_name)

    constructors: dict[str, TtsConstructor] = {
        DEFAULT_TTS_PROVIDER: MockTtsProvider,
        "kokoro": _build_kokoro,
    }

    try:
        constructor = constructors[provider_name]
    except KeyError:
        raise KeyError(
            f"Unknown TTS provider '{provider_name}'. "
            f"Registered providers: {', '.join(sorted(constructors))}."
        ) from None

    try:
        provider = constructor()
        logger.info(
            "create_tts_provider() created provider: name=%s type=%s",
            provider.name,
            type(provider).__name__,
        )
        return provider
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        if provider_name == DEFAULT_TTS_PROVIDER:
            raise
        logger.warning(
            "TTS provider '%s' failed to initialise: %s. Falling back to '%s'.",
            provider_name,
            exc,
            DEFAULT_TTS_PROVIDER,
        )
        return MockTtsProvider()


def _resolve_default() -> str:
    """Read the default TTS provider name from application settings."""
    try:
        from app.config.settings import get_settings

        return get_settings().tts_provider or DEFAULT_TTS_PROVIDER
    except Exception:  # noqa: BLE001 - settings not available
        return DEFAULT_TTS_PROVIDER


__all__ = ["DEFAULT_TTS_PROVIDER", "create_tts_provider"]

