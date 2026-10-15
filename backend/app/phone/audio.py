"""Call audio: raw 16-bit mono PCM in, WAV for Sarvam, and noticing when the caller stops talking.

Phone audio arrives as 20 ms chunks of 16 kHz signed 16-bit PCM ("audio/x-l16;rate=16000").
"""

import io
import math
import wave
from array import array

RATE = 16000
BYTES_PER_MS = RATE * 2 // 1000  # 32


def pcm_to_wav(pcm: bytes, rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def wav_to_pcm(wav: bytes) -> tuple[bytes, int]:
    """Raw PCM and its sample rate. Raises if the audio isn't 16-bit mono."""
    with wave.open(io.BytesIO(wav)) as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError("expected 16-bit mono WAV")
        return w.readframes(w.getnframes()), w.getframerate()


def chunks(pcm: bytes, rate: int, ms: int = 40) -> list[bytes]:
    """Split playback audio into ~40 ms pieces (Vobiz recommends 20–60 ms)."""
    size = rate * 2 * ms // 1000
    return [pcm[i:i + size] for i in range(0, len(pcm), size)]


def rms(pcm: bytes) -> float:
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


class EndOfSpeech:
    """Collects the caller's audio and says when one utterance is complete.

    Speech = a 20 ms frame noticeably louder than the line's background noise.
    An utterance ends after `silence_ms` of quiet following at least `min_speech_ms`
    of speech, or when it reaches `max_ms` (Sarvam handles up to ~30 s per request).
    """

    def __init__(self, silence_ms: int = 700, min_speech_ms: int = 250, max_ms: int = 25_000,
                 floor_rms: float = 300.0):
        self.silence_ms = silence_ms
        self.min_speech_ms = min_speech_ms
        self.max_ms = max_ms
        self.noise = floor_rms  # adapts to the line's background level
        self.floor = floor_rms
        self.reset()

    def reset(self) -> None:
        self.buf = bytearray()
        self.speech_ms = 0
        self.quiet_ms = 0
        self.pending = bytearray()

    @property
    def hearing_speech(self) -> bool:
        return self.speech_ms > 0

    def feed(self, pcm: bytes) -> bytes | None:
        """Add audio; returns the finished utterance (PCM) when the caller has stopped talking."""
        self.pending += pcm
        frame = 20 * BYTES_PER_MS
        while len(self.pending) >= frame:
            f, self.pending = bytes(self.pending[:frame]), self.pending[frame:]
            done = self._frame(f)
            if done is not None:
                return done
        return None

    def _frame(self, f: bytes) -> bytes | None:
        level = rms(f)
        loud = level > max(self.floor, self.noise * 2.5)
        if not loud:
            # Track background noise slowly so a fan or traffic doesn't count as speech.
            self.noise = 0.95 * self.noise + 0.05 * level
        if self.speech_ms == 0:
            if loud:
                self.speech_ms = 20
                self.buf += f
            return None
        self.buf += f
        if loud:
            self.speech_ms += 20
            self.quiet_ms = 0
        else:
            self.quiet_ms += 20
        total_ms = len(self.buf) // BYTES_PER_MS
        if (self.quiet_ms >= self.silence_ms and self.speech_ms >= self.min_speech_ms) or total_ms >= self.max_ms:
            out = bytes(self.buf)
            self.reset()
            return out
        if self.quiet_ms >= self.silence_ms:  # a click or cough, not speech
            self.reset()
        return None
