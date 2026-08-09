"""Sentrix Voice Assistant backend (Phase 16A).

This package adds a real-time voice layer to the existing AI pipeline. It is
deliberately a *separate* module: it only transcribes spoken audio into text
and routes that text into the existing conversation pipeline. It does not
touch the Planner, Tool Engine, Report Engine, Memory architecture, or the
existing text-chat flow.

Phase 16A scope
---------------
- WebSocket audio transport (``/api/v1/voice/transcribe``).
- Speech-to-Text provider abstraction with ``MockSttProvider`` as the default
  and an optional Faster-Whisper provider enabled only via configuration.
- Voice activity detection so a *single* transcription runs per utterance
  (rather than transcribing every audio chunk).
"""

from app.voice.schemas import (
    TextToSpeechRequest,
    VoiceClientEvent,
    VoiceEvent,
    VoiceEventType,
    VoiceServerEvent,
)
from app.voice.stt.base import SpeechToTextProvider
from app.voice.stt.factory import DEFAULT_STT_PROVIDER, create_stt_provider
from app.voice.stt.mock import MockSttProvider
from app.voice.tts.base import SpeechResult, TextToSpeechProvider
from app.voice.tts.factory import DEFAULT_TTS_PROVIDER, create_tts_provider
from app.voice.tts.mock import MockTtsProvider
from app.voice.vad import VoiceActivityDetector

__all__ = [
    "DEFAULT_STT_PROVIDER",
    "DEFAULT_TTS_PROVIDER",
    "MockSttProvider",
    "MockTtsProvider",
    "SpeechResult",
    "SpeechToTextProvider",
    "TextToSpeechProvider",
    "TextToSpeechRequest",
    "VoiceActivityDetector",
    "VoiceClientEvent",
    "VoiceEvent",
    "VoiceEventType",
    "VoiceServerEvent",
    "create_stt_provider",
    "create_tts_provider",
]
