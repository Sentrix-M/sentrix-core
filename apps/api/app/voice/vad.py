"""Voice Activity Detection (VAD) for the Sentrix Voice Assistant.

The voice WebSocket accumulates audio chunks while the user is speaking and
only runs STT a *single* time per utterance. :class:`VoiceActivityDetector`
decides when an utterance has ended so the handler can trigger one
transcription — avoiding unnecessary Whisper inference and reducing latency.

Design
------
- The detector works on raw PCM (16-bit little-endian mono) frames. The
  browser can send PCM16 frames (or we downsample from WAV/WebM to PCM16).
- ``add_frame`` computes the RMS energy of a frame and tracks a running
  speech/end-of-speech state.
- ``is_active`` reports whether the detector currently considers speech to be
  in progress.
- ``should_finalize`` returns ``True`` once a configurable silence window has
  elapsed after the last voiced frame, meaning the utterance has likely ended.

The detector is deliberately simple and dependency-free so it works offline
and is fully unit-testable. It is not a full-featured VAD (e.g. WebRTC VAD);
it is a lightweight energy-threshold gate sufficient for the MVP.
"""

from __future__ import annotations

import array
import struct
from dataclasses import dataclass, field


@dataclass
class VoiceActivityDetector:
    """Energy-threshold based voice activity detector.

    :param sample_rate: Audio sample rate (Hz). Default 16000.
    :param frame_ms: Frame size in milliseconds. Default 30.
    :param silence_ms: Silence duration required to declare end-of-speech.
    :param energy_threshold: RMS energy threshold above which a frame is
        considered voiced. Tune to the microphone/room.
    :param min_speech_ms: Minimum voiced duration before we consider that
        speech actually started (rejects transients).
    """

    sample_rate: int = 16000
    frame_ms: int = 30
    silence_ms: int = 500
    energy_threshold: float = 300.0
    min_speech_ms: int = 120

    _frame_size: int = field(init=False)
    _speech_ms: int = field(init=False, default=0)
    _silence_ms: int = field(init=False, default=0)
    _voiced: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        self._frame_size = int(self.sample_rate * self.frame_ms / 1000)

    def reset(self) -> None:
        """Reset the detector state for a new utterance."""
        self._speech_ms = 0
        self._silence_ms = 0
        self._voiced = False

    @property
    def is_active(self) -> bool:
        """Whether the detector currently considers speech in progress."""
        return self._voiced

    def add_frame(self, audio: bytes) -> bool:
        """Feed one PCM16 frame and update the speech state.

        :param audio: Raw 16-bit little-endian PCM samples for one frame.
        :returns: Whether the frame is classified as speech (voiced).
        """
        rms = self._rms(audio)
        voiced = rms >= self.energy_threshold

        if voiced:
            # Extend speech; reset the silence timer.
            self._speech_ms += self.frame_ms
            self._silence_ms = 0
            if self._speech_ms >= self.min_speech_ms:
                self._voiced = True
        else:
            self._silence_ms += self.frame_ms
            if self._voiced and self._silence_ms >= self.silence_ms:
                # Speech has ended.
                self._voiced = False
        return voiced

    def should_finalize(self) -> bool:
        """Return ``True`` when end-of-speech has been reached.

        The utterance is finalized when voice activity was detected and then
        a silence window elapsed (or the caller otherwise signals end via the
        ``end`` control message).
        """
        return not self._voiced and self._speech_ms >= self.min_speech_ms

    @staticmethod
    def _rms(audio: bytes) -> float:
        """Compute the RMS energy of raw PCM16 mono samples."""
        if not audio:
            return 0.0
        # Decode as signed 16-bit little-endian.
        samples = array.array("h")
        try:
            samples.frombytes(audio)
        except (struct.error, ValueError):
            # Fall back to unsigned byte interpretation if the frame is not
            # an exact multiple of 2 bytes (best effort).
            if not audio:
                return 0.0
            samples = array.array("h", (byte for byte in audio))

        if not samples:
            return 0.0
        total = sum(s * s for s in samples)
        return (total / len(samples)) ** 0.5


__all__ = ["VoiceActivityDetector"]

