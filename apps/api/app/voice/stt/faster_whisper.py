"""Optional local Faster-Whisper STT provider for the Sentrix Voice Assistant.

:class:`FasterWhisperProvider` runs a local Faster-Whisper model for offline,
on-device speech recognition. It is *optional* — it is only constructed when
``STT_PROVIDER=faster_whisper`` is set, so it is never forced on developer
machines (the default remains the offline :class:`MockSttProvider`).

The heavy model is loaded lazily in :meth:`load` (called once before the
first transcription) so importing this module does not pull in the model or
its runtime. The ``faster-whisper`` package is an optional dependency and
only needed when this provider is selected.

Audio notes
-----------
The browser streams WebM/Opus (or MP4/AAC on Safari) container bytes over the
WebSocket. Faster-Whisper expects a decodable audio file, and writing raw
container bytes to a ``.wav``-named temp file is invalid. We therefore first
transcode the incoming container to a 16-bit mono 16 kHz WAV using the static
ffmpeg binary shipped with ``imageio-ffmpeg`` (Windows-compatible, no system
install), then feed that WAV to the model.
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import tempfile
from typing import Any

from app.config.settings import Settings, get_settings
from app.voice.stt.base import TranscriptionResult

logger = logging.getLogger(__name__)

#: Target output format for the pre-transcription decode.
_WAV_SAMPLE_RATE = 16000
_WAV_CHANNELS = 1
_WAV_BITS = 16


def _get_ffmpeg_path() -> str:
    """Resolve the bundled static ffmpeg binary (imageio-ffmpeg)."""
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def decode_to_wav(audio: bytes) -> bytes:
    """Transcode raw browser audio bytes (WebM/Opus) to a PCM16 WAV.

    Uses the static ffmpeg bundled with ``imageio-ffmpeg`` so no system
    ffmpeg install is required and the binary is Windows-compatible.

    :param audio: Raw audio container bytes (e.g. WebM/Opus) for one utterance.
    :returns: A complete WAV file (RIFF/WAVE, PCM16, mono, 16 kHz).
    :raises RuntimeError: If ffmpeg is unavailable or the transcode fails.
    """
    if not audio:
        raise RuntimeError("No audio bytes provided to decode.")

    ffmpeg = _get_ffmpeg_path()
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as inp:
        inp.write(audio)
        in_path = inp.name
    out_fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(out_fd)

    try:
        cmd = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            in_path,
            "-vn",
            "-ac",
            str(_WAV_CHANNELS),
            "-ar",
            str(_WAV_SAMPLE_RATE),
            "-sample_fmt",
            "s16",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if not os.path.exists(out_path) or result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg transcode failed (rc={result.returncode}): {result.stderr[-500:]}"
            )
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        with contextlib.suppress(OSError):
            os.remove(in_path)
        with contextlib.suppress(OSError):
            os.remove(out_path)


class FasterWhisperProvider:
    """Local Faster-Whisper speech-to-text provider (optional).

    :param model_name: Faster-Whisper model size (e.g. "base", "small",
        "medium"). Defaults to :class:`Settings.whisper_model`.
    :param device: Compute device ("cpu" default, or "cuda").
        Defaults to :class:`Settings.whisper_device`.
    :param compute_type: Precision ("int8" default).
        Defaults to :class:`Settings.whisper_compute_type`.
    """

    name = "faster_whisper"

    def __init__(
        self,
        *,
        model_name: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ) -> None:
        cfg: Settings = get_settings()
        self._model_name = model_name or cfg.whisper_model
        self._device = device or cfg.whisper_device
        self._compute_type = compute_type or cfg.whisper_compute_type
        self._model: Any | None = None

    async def load(self) -> None:
        """Load the Faster-Whisper model (idempotent).

        The import is deferred so ``faster-whisper`` is only required when
        this provider is actually used. Model downloads happen on first load
        and are cached on disk by Faster-Whisper.
        """
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001 - report cleanly
            raise RuntimeError(
                "faster-whisper is not installed. Install it via "
                "`pip install sentrix-api[voice]` or set STT_PROVIDER=mock."
            ) from exc

        logger.info(
            "Loading Faster-Whisper model=%s device=%s compute_type=%s",
            self._model_name,
            self._device,
            self._compute_type,
        )
        # Sync model load blocks briefly the first time; acceptable on init.
        self._model = WhisperModel(
            self._model_name,
            device=self._device,
            compute_type=self._compute_type,
        )

    def _transcribe_sync(self, wav_path: str):
        """Run the model on a decoded WAV file (synchronous core)."""
        if self._model is None:
            raise RuntimeError("Faster-Whisper model failed to load.")
        return self._model.transcribe(
            wav_path,
            language=None,  # auto-detect
            vad_filter=True,
        )

    async def transcribe(self, audio: bytes) -> TranscriptionResult:
        """Transcribe ``audio`` with the local Faster-Whisper model.

        :param audio: Raw audio container bytes (e.g. WebM/Opus) for one
            utterance. The bytes are transcoded to a PCM16 mono 16 kHz WAV
            before being passed to the model.
        :returns: A :class:`TranscriptionResult` with the recognised text.
        :raises RuntimeError: If the model is unavailable or decoding fails.
        """
        if self._model is None:
            await self.load()
        if self._model is None:
            raise RuntimeError("Faster-Whisper model failed to load.")

        # Transcode the browser container (WebM/Opus) to a valid PCM16 WAV.
        wav = decode_to_wav(audio)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav)
            tmp_path = tmp.name
        try:
            segments, info = self._transcribe_sync(tmp_path)
            text = " ".join(seg.text.strip() for seg in segments if seg.text).strip()
            return TranscriptionResult(
                text=text,
                confidence=getattr(info, "avg_logprob", None),
                provider=self.name,
                metadata={
                    "language": getattr(info, "language", None),
                    "duration": getattr(info, "duration", None),
                },
            )
        finally:
            with contextlib.suppress(OSError):
                os.remove(tmp_path)

    async def close(self) -> None:
        """Release the model reference."""
        self._model = None


__all__ = ["FasterWhisperProvider", "decode_to_wav"]
