"""Speech-to-Text provider abstraction for the Sentrix Voice Assistant.

:class:`SpeechToTextProvider` is a small Protocol any STT backend must
implement. It keeps the voice WebSocket layer decoupled from concrete
speech engines (Faster-Whisper, cloud APIs like OpenAI Realtime, ...), so new
backends can be registered without touching the transport or the pipeline.

.. note::
    The provider only runs on *complete utterances* (after voice-activity
    detection signals end-of-speech). The WebSocket handler is responsible
    for accumulating audio chunks and deciding when to call :meth:`transcribe`
    a single time — the provider never sees every raw chunk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class TranscriptionResult:
    """The outcome of a single speech-to-text run."""

    text: str
    #: Optional per-segment confidence, 0..1. ``None`` when not available.
    confidence: float | None = None
    #: Provider name, for diagnostics/logging.
    provider: str = "unknown"
    #: Reserved for optional metadata (language, duration, ...).
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """Whether the transcription produced no usable text."""
        return not self.text.strip()


class SpeechToTextProvider(Protocol):
    """Contract implemented by every Sentrix STT backend."""

    name: str

    async def transcribe(self, audio: bytes) -> TranscriptionResult:
        """Transcribe a complete audio utterance into text.

        :param audio: The accumulated audio bytes (e.g. WAV/WebM) for one
            utterance.
        :returns: A :class:`TranscriptionResult` with the recognised text.
        """
        ...

    async def load(self) -> None:
        """Load any heavy resources (e.g. a model) when needed.

        Called once, lazily, before the first transcription. Providers that
        require no model (e.g. the mock) can no-op.
        """
        ...

    async def close(self) -> None:
        """Release any resources held by the provider."""
        ...


__all__ = ["SpeechToTextProvider", "TranscriptionResult"]
