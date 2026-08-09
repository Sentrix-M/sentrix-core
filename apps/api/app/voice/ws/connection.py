"""Voice WebSocket connection helpers.

This module holds the small per-connection state used while accumulating an
audio utterance: the assigned ``conversation_id``, the running audio buffer
for the current utterance, the voice-activity detector, and the STT provider.
It keeps the endpoint handler lean by moving the accumulation logic here.
"""

from __future__ import annotations

from app.voice.stt.base import SpeechToTextProvider
from app.voice.vad import VoiceActivityDetector


class VoiceConnection:
    """Mutable per-connection state for one voice WebSocket.

    :param stt_provider: The speech-to-text provider used for this session.
    :param vad: Optional voice-activity detector. Defaults to a fresh
        :class:`VoiceActivityDetector`.
    :param conversation_id: Optional client-provided conversation id. When a
        ``config`` event arrives, ``conversation_id`` is reset to that value.
    """

    def __init__(
        self,
        stt_provider: SpeechToTextProvider,
        *,
        vad: VoiceActivityDetector | None = None,
        conversation_id: str | None = None,
    ) -> None:
        self.stt_provider = stt_provider
        self.vad = vad or VoiceActivityDetector()
        self.conversation_id = conversation_id
        #: Accumulated raw audio bytes for the *current* utterance.
        self._audio_buffer = bytearray()
        #: Byte offset into ``_audio_buffer`` already fed to the VAD. Kept
        #: separate from the buffer so VAD processing never destroys the
        #: audio required for the final transcription.
        self._vad_cursor = 0

    @property
    def audio_buffer(self) -> bytes:
        """The raw bytes accumulated so far for the current utterance."""
        return bytes(self._audio_buffer)

    def reset_utterance(self) -> None:
        """Clear the audio buffer and reset the VAD for a new utterance."""
        self._audio_buffer.clear()
        self._vad_cursor = 0
        self.vad.reset()

    def add_audio(self, audio: bytes) -> bool:
        """Append audio bytes and feed them to the VAD.

        Frames are sliced from the accumulated buffer and passed to the VAD
        so end-of-speech is detected *while* audio streams in, without
        requiring the client to send a separate ``end`` message. All received
        audio is preserved in ``_audio_buffer`` for the final transcription;
        only a read cursor advances across the VAD frames.

        :param audio: Raw PCM16 audio bytes to accumulate.
        :returns: Whether this chunk flipped the VAD to ``active`` (speech
            started). The caller can use this to gate transcription.
        """
        self._audio_buffer.extend(audio)

        activated = False
        frame_size = self.vad._frame_size  # noqa: SLF001 - internal access
        if frame_size <= 0:
            return False
        # Feed complete frames (from the cursor forward) to the VAD.
        while self._vad_cursor + frame_size <= len(self._audio_buffer):
            frame = bytes(
                self._audio_buffer[self._vad_cursor : self._vad_cursor + frame_size]
            )
            voiced = self.vad.add_frame(frame)
            if voiced:
                activated = True
            self._vad_cursor += frame_size

        return activated


__all__ = ["VoiceConnection"]
