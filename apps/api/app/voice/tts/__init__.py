"""Text-to-Speech providers for the Sentrix Voice Assistant (Phase 16C).

This subpackage adds a natural voice-output layer to the existing AI pipeline.
It is deliberately a *separate* module: it only converts a completed assistant
message into audio via an abstract :class:`TextToSpeechProvider`. It does not
touch the Planner, Tool Engine, Report Engine, Memory architecture, or the
existing text-chat flow.

Backends
--------
- ``mock`` (default) — deterministic, offline-safe WAV audio.
- ``kokoro`` — local Kokoro TTS, enabled only via ``TTS_PROVIDER=kokoro``.
Future providers (OpenAI, ElevenLabs, Piper) plug in the same way.
"""

from app.voice.tts.base import SpeechResult, TextToSpeechProvider
from app.voice.tts.factory import DEFAULT_TTS_PROVIDER, create_tts_provider
from app.voice.tts.kokoro import KokoroTTSProvider
from app.voice.tts.mock import MockTtsProvider

__all__ = [
    "DEFAULT_TTS_PROVIDER",
    "KokoroTTSProvider",
    "MockTtsProvider",
    "SpeechResult",
    "TextToSpeechProvider",
    "create_tts_provider",
]
