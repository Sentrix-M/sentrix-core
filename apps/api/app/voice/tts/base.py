"""Text-to-Speech provider abstraction for the Sentrix Voice Assistant.

:class:`TextToSpeechProvider` is a small Protocol any TTS backend must
implement. It keeps the HTTP TTS layer (``/api/v1/tts/synthesize``) decoupled
from concrete speech engines (Kokoro, OpenAI, ElevenLabs, Piper, ...), so new
backends can be registered without touching the transport or the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class SpeechResult:
    """The outcome of a single text-to-speech synthesis run."""

    #: The synthesised audio bytes (e.g. WAV/PCM/OGG).
    audio: bytes
    #: IANA media type for ``audio`` (e.g. ``audio/wav``).
    media_type: str = "audio/wav"
    #: Provider name, for diagnostics/logging.
    provider: str = "unknown"
    #: Reserved for optional metadata (duration, sample rate, language, ...).
    metadata: dict[str, object] = field(default_factory=dict)


class TextToSpeechProvider(Protocol):
    """Contract implemented by every Sentrix TTS backend."""

    name: str

    async def synthesize(self, text: str) -> SpeechResult:
        """Convert ``text`` into natural-sounding audio.

        :param text: The text to speak (a completed assistant message).
        :returns: A :class:`SpeechResult` with the encoded audio bytes.
        """
        ...

    async def load(self) -> None:
        """Load any heavy resources (e.g. a model) when needed.

        Called once, lazily, before the first synthesis. Providers that
        require no model (e.g. the mock) can no-op.
        """
        ...

    async def close(self) -> None:
        """Release any resources held by the provider."""
        ...


__all__ = ["SpeechResult", "TextToSpeechProvider"]

