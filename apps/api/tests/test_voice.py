"""Unit and integration tests for the Sentrix Voice Assistant (Phase 16A).

Covers the STT provider factory, the mock STT provider, the voice-activity
detector, the connection helper, the WebM→WAV decoder (Phase 18 Step 3), the
Faster-Whisper provider (with a mocked model), and the HTTP WebSocket endpoint
``/api/v1/voice/transcribe``.

The WebSocket tests use a real ``TestClient`` with the application lifespan
executed so the user/refresh-token repositories are seeded and
``build_kernel_pipeline`` resolves the offline ``MockProvider`` (see
``conftest.py`` for the forced deterministic settings).
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from app.main import app
from app.voice.stt.base import TranscriptionResult
from app.voice.stt.factory import create_stt_provider
from app.voice.stt.faster_whisper import FasterWhisperProvider, decode_to_wav
from app.voice.stt.mock import MockSttProvider
from app.voice.vad import VoiceActivityDetector
from app.voice.ws.connection import VoiceConnection

ADMIN_EMAIL = "admin@sentrix.io"
ADMIN_PASSWORD = "ChangeMe_123!"


def _next_event_until(ws, terminal: set[str]) -> dict:
    """Read server events until one of ``terminal`` event types is seen.

    The handler sends a ``status`` ("connected") event on accept, so callers
    need to drain non-terminal events before asserting on the outcome.
    """
    while True:
        text = ws.receive_text()
        if not text:
            continue
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            continue
        if event.get("type") in terminal:
            return event


@pytest.fixture(scope="module")
def client():
    """Return a TestClient with the application lifespan executed."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client) -> str:
    """Log in as the seeded admin and return the access token."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _make_sine_wav(duration_s: float = 0.2, sample_rate: int = 16000) -> bytes:
    """Build a tiny valid PCM16 mono WAV (used as a decode fixture)."""
    import math
    import struct

    n = int(duration_s * sample_rate)
    data = bytearray()
    for i in range(n):
        sample = int(12000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        data += struct.pack("<h", sample)
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    header += b"fmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(data))
    return header + bytes(data)


# ---------------------------------------------------------------------------
# STT provider factory
# ---------------------------------------------------------------------------


class TestSttFactory:
    def test_default_provider_is_mock(self) -> None:
        provider = create_stt_provider()
        assert isinstance(provider, MockSttProvider)

    def test_mock_provider_transcribes(self) -> None:
        provider = create_stt_provider()
        result = asyncio.run(provider.transcribe(b"\x00\x00"))
        assert isinstance(result, TranscriptionResult)
        assert result.text

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(KeyError):
            create_stt_provider("bogus")


# ---------------------------------------------------------------------------
# Mock STT provider
# ---------------------------------------------------------------------------


class TestMockStt:
    def test_transcribe_returns_default_text(self) -> None:
        provider = MockSttProvider(default_transcript="scan the host")
        result = asyncio.run(provider.transcribe(b"\x00\x00"))
        assert result.text == "scan the host"

    def test_load_and_close_are_noops(self) -> None:
        provider = MockSttProvider()
        asyncio.run(provider.load())
        asyncio.run(provider.close())


# ---------------------------------------------------------------------------
# Voice activity detector
# ---------------------------------------------------------------------------


class TestVad:
    def test_silent_frame_is_not_voiced(self) -> None:
        vad = VoiceActivityDetector()
        frame = b"\x00\x00" * 2
        assert vad.add_frame(frame) is False
        assert vad.is_active is False

    def test_reset_clears_state(self) -> None:
        vad = VoiceActivityDetector()
        vad.add_frame(b"\x00\x00" * 2)
        vad.reset()
        assert vad.is_active is False


# ---------------------------------------------------------------------------
# VoiceConnection helper
# ---------------------------------------------------------------------------


class TestVoiceConnection:
    def test_accumulates_audio(self) -> None:
        provider = MockSttProvider()
        conn = VoiceConnection(stt_provider=provider, vad=VoiceActivityDetector())
        conn.add_audio(b"\xff\x01")
        assert conn.audio_buffer

    def test_audio_buffer_preserved_after_vad_processing(self) -> None:
        """VAD must not destroy the buffered audio needed for transcription."""
        provider = MockSttProvider()
        conn = VoiceConnection(stt_provider=provider, vad=VoiceActivityDetector())
        # Provide enough PCM16 frames so the VAD consumes several of them.
        frame_size = conn.vad._frame_size  # noqa: SLF001 - test access
        chunk = b"\x00\x00" * frame_size
        for _ in range(5):
            conn.add_audio(chunk)
        # The full buffer must still be available for STT.
        assert len(conn.audio_buffer) >= frame_size * 5

    def test_audio_buffer_after_multiple_chunks_of_frame_size(self) -> None:
        """Feeding many full frames must not empty the audio buffer."""
        provider = MockSttProvider()
        conn = VoiceConnection(stt_provider=provider, vad=VoiceActivityDetector())
        frame_size = conn.vad._frame_size  # noqa: SLF001 - test access
        for _ in range(10):
            conn.add_audio(b"\xff\x00" * frame_size)
        assert len(conn.audio_buffer) == frame_size * 20

    def test_reset_utterance_clears_buffer(self) -> None:
        provider = MockSttProvider()
        conn = VoiceConnection(stt_provider=provider, vad=VoiceActivityDetector())
        conn.add_audio(b"\xff\x01\x00\x00")
        conn.reset_utterance()
        assert conn.audio_buffer == b""


# ---------------------------------------------------------------------------
# Audio decoder (WebM/Opus → WAV) — Phase 18 Step 3
# ---------------------------------------------------------------------------


class TestAudioDecoder:
    """Prove ``decode_to_wav`` returns a valid RIFF/WAVE PCM16 mono 16kHz WAV."""

    def test_decode_produces_valid_wav_header(self) -> None:
        """A browser-like WebM container decodes to a valid WAV header."""
        import os
        import subprocess
        import tempfile

        import imageio_ffmpeg

        wav = _make_sine_wav()
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as inp:
            inp.write(wav)
            in_path = inp.name
        out_fd, out_path = tempfile.mkstemp(suffix=".webm")
        os.close(out_fd)
        try:
            subprocess.run(
                [ffmpeg, "-y", "-loglevel", "error", "-i", in_path, "-vn", out_path],
                check=True,
                capture_output=True,
            )
            with open(out_path, "rb") as fh:
                webm = fh.read()
        finally:
            os.remove(in_path)
            if os.path.exists(out_path):
                os.remove(out_path)

        assert webm, "Failed to produce a WebM test fixture."

        decoded = decode_to_wav(webm)
        assert decoded[:4] == b"RIFF"
        assert decoded[8:12] == b"WAVE"
        assert decoded[12:16] == b"fmt "
        assert decoded[20:22] == b"\x01\x00"  # PCM format
        assert decoded[22:24] == b"\x01\x00"  # mono
        assert decoded[24:28] == b"\x80\x3e\x00\x00"  # 16000 Hz

    def test_decode_rejects_empty_audio(self) -> None:
        with pytest.raises(RuntimeError):
            decode_to_wav(b"")


# ---------------------------------------------------------------------------
# Faster-Whisper provider (model mocked — no download)
# ---------------------------------------------------------------------------


class TestFasterWhisperProvider:
    def test_transcribe_uses_mocked_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """transcribe() must succeed without downloading a Whisper model."""
        provider = FasterWhisperProvider(model_name="tiny")
        provider._model = object()  # simulate a loaded model without downloading

        class FakeSegment:
            text = "check the latest security alerts"

        class FakeInfo:
            avg_logprob = -0.5
            language = "en"
            duration = 1.0

        captured: dict = {}

        def fake_transcribe(path, _language=None, vad_filter=True):
            captured["path"] = path
            captured["vad_filter"] = vad_filter
            return [FakeSegment()], FakeInfo()

        monkeypatch.setattr(provider, "_transcribe_sync", fake_transcribe)

        result = asyncio.run(provider.transcribe(_make_sine_wav()))
        assert result.text == "check the latest security alerts"
        assert result.provider == "faster_whisper"
        assert result.confidence == -0.5
        # The model must be handed a WAV path (not raw container bytes).
        assert captured["path"].endswith(".wav")
        assert captured["vad_filter"] is True

    def test_load_requires_faster_whisper_installed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the package is missing, load() raises a clear RuntimeError."""
        provider = FasterWhisperProvider(model_name="tiny")

        import builtins

        real_import = builtins.__import__

        def raiser():
            raise ImportError("no module named faster_whisper")

        def guarded_import(name, *args, **kwargs):
            if name == "faster_whisper":
                raiser()
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", guarded_import)
        with pytest.raises(RuntimeError, match="faster-whisper"):
            asyncio.run(provider.load())


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


class TestVoiceEndpoint:
    def test_rejects_without_token(self, client) -> None:
        with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect(
            "/api/v1/voice/transcribe"
        ) as ws:
            ws.receive_text()
        assert exc_info.value.code == 1008

    def test_full_transcribe_flow(self, client, admin_token: str) -> None:
        """Send audio, an end event, and expect transcript + response + done."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        with client.websocket_connect(
            "/api/v1/voice/transcribe", headers=headers
        ) as ws:
            # 1. config event to set the conversation id.
            ws.send_text(
                json.dumps(
                    {
                        "type": "config",
                        "conversation_id": f"voice-{uuid.uuid4().hex[:8]}",
                    }
                )
            )

            # 2. Send audio bytes (binary frame).
            ws.send_bytes(b"\x00\x00\x00\x00" * 64)

            # 3. Send the end-of-speech event.
            ws.send_text(json.dumps({"type": "end"}))

            # 4. Collect server events until we see done.
            events: list[dict] = []
            while True:
                text = ws.receive_text()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    continue
                events.append(event)
                if event.get("type") == "done":
                    break

            types = [e.get("type") for e in events]
            assert "status" in types
            assert "transcript" in types
            assert "response" in types
            assert "done" in types

    def test_transcript_final_is_emitted(self, client, admin_token: str) -> None:
        """Send audio+end and verify a final transcript event is emitted."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        with client.websocket_connect(
            "/api/v1/voice/transcribe", headers=headers
        ) as ws:
            ws.send_bytes(b"\x00\x00\x00\x00" * 64)
            ws.send_text(json.dumps({"type": "end"}))

            transcript_event: dict | None = None
            while True:
                text = ws.receive_text()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "transcript":
                    transcript_event = event
                if event.get("type") == "done":
                    break

            # ``to_dict()`` flattens ``extra`` to the top level, so ``final``
            # is a top-level key on the wire.
            assert transcript_event is not None
            assert transcript_event.get("text")
            assert transcript_event.get("final") is True

    def test_error_when_no_audio(self, client, admin_token: str) -> None:
        headers = {"Authorization": f"Bearer {admin_token}"}
        with client.websocket_connect(
            "/api/v1/voice/transcribe", headers=headers
        ) as ws:
            ws.send_text(json.dumps({"type": "end"}))
            event = _next_event_until(ws, {"error"})
            assert event["type"] == "error"

    def test_auth_via_query_token(self, client, admin_token: str) -> None:
        with client.websocket_connect(
            f"/api/v1/voice/transcribe?token={admin_token}"
        ) as ws:
            ws.send_text(json.dumps({"type": "end"}))
            event = _next_event_until(ws, {"error"})
            # No audio -> clean error (auth succeeded).
            assert event["type"] == "error"
