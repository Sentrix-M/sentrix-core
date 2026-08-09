"""Deterministic offline Mock TTS provider.

:class:`MockTtsProvider` is the default text-to-speech backend. It performs
no real speech synthesis — it returns deterministic, offline-safe WAV audio so
the HTTP TTS layer and the browser playback path are fully testable and the app
runs without downloading a Kokoro model or calling a cloud TTS API.

The generated WAV is a silent PCM encoded block (sample rate 24000 Hz, mono,
16-bit) so it is a real, playable ``audio/wav`` blob while requiring no heavy
dependencies.
"""

from __future__ import annotations

import wave
from io import BytesIO

from app.voice.tts.base import SpeechResult

_DEFAULT_SAMPLE_RATE = 24000
_DEFAULT_DURATION_S = 0.25


def _silent_wav(duration_s: float = _DEFAULT_DURATION_S) -> bytes:
    """Build a valid, silent PCM WAV blob (mono, 16-bit)."""
    sample_rate = _DEFAULT_SAMPLE_RATE
    n_frames = int(sample_rate * duration_s)
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * n_frames)
    return buffer.getvalue()


class MockTtsProvider:
    """Offline, deterministic text-to-speech provider (dev/test default)."""

    name = "mock"

    def __init__(self, duration_s: float = _DEFAULT_DURATION_S) -> None:
        """Build the mock provider.

        :param duration_s: Duration in seconds of the returned WAV audio.
        """
        self._duration_s = duration_s

    async def synthesize(self, text: str) -> SpeechResult:
        """Return a playable silent WAV blob for ``text``.

        The audio bytes are deterministic; no real speech is synthesised.
        """
        return SpeechResult(
            audio=_silent_wav(self._duration_s),
            media_type="audio/wav",
            provider="mock",
            metadata={"text_length": len(text or "")},
        )

    async def load(self) -> None:
        """No-op — the mock requires no model or resources."""

    async def close(self) -> None:
        """No-op — the mock holds no resources."""


__all__ = ["_DEFAULT_SAMPLE_RATE", "MockTtsProvider"]

