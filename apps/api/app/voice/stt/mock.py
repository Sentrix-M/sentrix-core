"""Deterministic offline Mock STT provider.

:class:`MockSttProvider` is the default speech-to-text backend. It performs
no real speech recognition — it returns deterministic, offline-safe text so
the voice WebSocket layer is fully testable and the app runs without
downloading a Whisper model. It never requires network or heavy dependencies.
"""

from __future__ import annotations

import hashlib

from app.voice.stt.base import TranscriptionResult

#: Fixed transcript returned by default (kept deterministic for tests). The
#: mock recognises a small set of scripted phrases for a few demo utterances,
#: otherwise it returns a generic acknowledgement.
_DEFAULT_TRANSCRIPT = "Check the latest security alerts"

#: Public alias exported in ``__all__`` for callers that want the default.
DEFAULT_TRANSCRIPT = _DEFAULT_TRANSCRIPT


class MockSttProvider:
    """Offline, deterministic speech-to-text provider (dev/test default)."""

    name = "mock"

    #: Optional mapping of phrase keys to canned transcripts for demos/tests.
    #: Keys are truncated SHA-1 of the audio bytes so a test can request a
    #: specific mock transcript deterministically.
    _scripted: dict[str, str] = {
        hashlib.sha1(b"mock-alerts").hexdigest()[:16]: "Check the latest security alerts",
        hashlib.sha1(b"mock-vt").hexdigest()[:16]: "Check VirusTotal for 8.8.8.8",
        hashlib.sha1(b"mock-shodan").hexdigest()[:16]: "Run a Shodan lookup",
    }

    def __init__(self, default_transcript: str | None = None) -> None:
        """Build the mock provider.

        :param default_transcript: Transcript returned when no scripted phrase
            matches ``audio``. Defaults to :data:`_DEFAULT_TRANSCRIPT`.
        """
        self._default = default_transcript or _DEFAULT_TRANSCRIPT

    async def transcribe(self, audio: bytes) -> TranscriptionResult:
        """Return a deterministic transcript derived from ``audio``.

        If ``audio`` maps to a scripted phrase, that transcript is returned;
        otherwise the configured default is returned. Never performs real
        speech recognition.
        """
        key = hashlib.sha1(audio).hexdigest()[:16]
        text = self._scripted.get(key, self._default)
        return TranscriptionResult(text=text, provider="mock", confidence=1.0)

    async def load(self) -> None:
        """No-op — the mock requires no model or resources."""

    async def close(self) -> None:
        """No-op — the mock holds no resources."""


__all__ = ["DEFAULT_TRANSCRIPT", "MockSttProvider"]
