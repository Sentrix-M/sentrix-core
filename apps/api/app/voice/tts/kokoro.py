"""Optional Kokoro TTS provider.

:class:`KokoroTTSProvider` integrates the local `kokoro` text-to-speech
package. It is **never** constructed unless explicitly requested via
``TTS_PROVIDER=kokoro`` (see :func:`app.voice.tts.factory.create_tts_provider`).

The provider is deliberately lazy: the heavy ``kokoro`` import happens at
construction time, so the rest of the app stays lightweight when the mock
(default) is selected. If the package or model is unavailable, the constructor
raises and the factory gracefully falls back to :class:`MockTtsProvider`.
"""

from __future__ import annotations

import logging

from app.voice.tts.base import SpeechResult

logger = logging.getLogger(__name__)

#: Default sample rate used when the model does not report one.
_DEFAULT_SAMPLE_RATE = 24000


class KokoroTTSProvider:
    """Local Kokoro text-to-speech provider (optional)."""

    name = "kokoro"

    def __init__(self, voice: str = "af_default") -> None:
        """Build the Kokoro provider.

        The ``kokoro`` package is imported here so a missing dependency fails
        fast at construction time (allowing the factory to fall back to mock).

        :param voice: Kokoro voice identifier (e.g. ``af_default``).
        :raises ImportError: When the ``kokoro`` package is not installed.
        """
        self._voice = voice
        self._model = None
        self._pipeline = None
        self._load_kokoro()

    def _load_kokoro(self) -> None:
        """Import and construct the Kokoro model + pipeline (lazy/heavy)."""
        try:
            import kokoro  # noqa: F401 - only imported when explicitly selected
        except Exception as exc:  # noqa: BLE001 - surface as a construction error
            raise ImportError(
                "Kokoro TTS is not installed. Run `pip install kokoro` and set "
                "TTS_PROVIDER=kokoro to enable it."
            ) from exc

        # Kokoro's exact API varies by version; we keep a thin, defensive
        # envelope so the app never hard-depends on a volatile interface.
        try:
            from kokoro import KPipeline  # type: ignore[import-not-found]

            self._pipeline = KPipeline(lang_code="a")
            self._model = {"engine": "kokoro", "pipeline": self._pipeline}
        except Exception as exc:  # noqa: BLE001 - construction failed
            raise ImportError(f"Failed to initialise Kokoro TTS: {exc}") from exc

    async def synthesize(self, text: str) -> SpeechResult:
        """Synthesise ``text`` into Kokoro audio.

        The pipeline is invoked in a worker thread (``asyncio.to_thread``) so
        the event loop is never blocked by CPU-bound inference. Audio is
        returned as raw 24000 Hz mono PCM in a WAV envelope.
        """
        if self._pipeline is None:
            raise RuntimeError("Kokoro TTS pipeline is not initialised.")

        wav_bytes = await self._synthesize_thread(text)
        return SpeechResult(
            audio=wav_bytes,
            media_type="audio/wav",
            provider="kokoro",
            metadata={"voice": self._voice, "sample_rate": _DEFAULT_SAMPLE_RATE},
        )

    async def _synthesize_thread(self, text: str) -> bytes:
        """Run Kokoro inference in a worker thread and wrap it as WAV."""
        import asyncio

        return await asyncio.to_thread(self._run_kokoro, text)

    def _run_kokoro(self, text: str) -> bytes:
        """Run the Kokoro pipeline synchronously and return WAV bytes."""
        import io
        import wave

        # Collect all generated audio segments and concatenate them.
        segments = []
        for result in self._pipeline(  # type: ignore[union-attr]
            text.strip() or " ",
            voice=self._voice,
        ):
            # Kokoro yields KPipeline.Result objects exposing a float32
            # 24000 Hz ``audio`` tensor (>= 0.9.x). Older versions exposed the
            # audio as a plain tuple element; both are handled defensively.
            item = result
            if hasattr(item, "audio") and item.audio is not None:
                segments.append(item.audio)
            elif isinstance(item, (tuple, list)) and len(item) >= 2:
                segments.append(item[1])
            else:
                logger.warning("Kokoro produced a segment without audio; skipping.")

        if not segments:
            raise RuntimeError("Kokoro produced no audio for the given text.")

        import numpy

        audio = numpy.concatenate(segments)
        pcm = (audio * 32767.0).clip(-32768, 32767).astype(numpy.int16).tobytes()

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(_DEFAULT_SAMPLE_RATE)
            wav.writeframes(pcm)
        return buffer.getvalue()

    async def load(self) -> None:
        """No-op — Kokoro is loaded eagerly at construction time."""

    async def close(self) -> None:
        """Release any resources held by the Kokoro provider."""
        self._pipeline = None
        self._model = None


__all__ = ["KokoroTTSProvider"]
