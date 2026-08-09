"""Speech-to-Text provider factory for the Sentrix Voice Assistant.

:func:`create_stt_provider` builds an STT backend by name, mirroring the
existing :class:`~app.providers.factory.ProviderFactory` pattern. The default
is the offline, deterministic :class:`MockSttProvider` so the voice layer
works on any machine with no heavy model. Faster-Whisper is only constructed
when explicitly requested via ``STT_PROVIDER`` — it is never forced on
developer machines.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.voice.stt.base import SpeechToTextProvider
from app.voice.stt.mock import MockSttProvider

logger = logging.getLogger(__name__)

#: Provider name used when no explicit STT provider is requested.
DEFAULT_STT_PROVIDER = "mock"


class SttConstructor(Protocol):
    """Callable that builds a :class:`SpeechToTextProvider` instance."""

    def __call__(self) -> SpeechToTextProvider:
        """Return a configured STT provider instance."""
        ...


def _build_faster_whisper() -> SpeechToTextProvider:
    """Construct a :class:`~app.voice.stt.faster_whisper.FasterWhisperProvider`.

    The import is deferred so ``faster-whisper`` is only required when this
    provider is actually selected. If the package (or model) is unavailable,
    the constructor raises and the factory degrades to the mock.
    """
    from app.voice.stt.faster_whisper import FasterWhisperProvider

    return FasterWhisperProvider()


def create_stt_provider(name: str | None = None) -> SpeechToTextProvider:
    """Return a configured STT provider instance.

    :param name: Provider name. Defaults to the ``STT_PROVIDER`` setting or
        :data:`DEFAULT_STT_PROVIDER`.
    :raises KeyError: When ``name`` is not a registered provider and no
        fallback is available.
    """
    provider_name = name or _resolve_default()
    logger.info("create_stt_provider() — requested provider: %s", provider_name)

    constructors: dict[str, SttConstructor] = {
        DEFAULT_STT_PROVIDER: MockSttProvider,
        "faster_whisper": _build_faster_whisper,
    }

    try:
        constructor = constructors[provider_name]
    except KeyError:
        raise KeyError(
            f"Unknown STT provider '{provider_name}'. "
            f"Registered providers: {', '.join(sorted(constructors))}."
        ) from None

    try:
        provider = constructor()
        logger.info(
            "create_stt_provider() created provider: name=%s type=%s",
            provider.name,
            type(provider).__name__,
        )
        return provider
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        if provider_name == DEFAULT_STT_PROVIDER:
            raise
        logger.warning(
            "STT provider '%s' failed to initialise: %s. Falling back to '%s'.",
            provider_name,
            exc,
            DEFAULT_STT_PROVIDER,
        )
        return MockSttProvider()


def _resolve_default() -> str:
    """Read the default STT provider name from application settings."""
    try:
        from app.config.settings import get_settings

        return get_settings().stt_provider or DEFAULT_STT_PROVIDER
    except Exception:  # noqa: BLE001 - settings not available
        return DEFAULT_STT_PROVIDER


__all__ = ["DEFAULT_STT_PROVIDER", "create_stt_provider"]
