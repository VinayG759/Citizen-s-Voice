"""Sarvam: the ears (speech → text) and the mouth (text → speech). Nothing else."""

import base64
import io
import time
import wave
from dataclasses import dataclass

import httpx

from app.settings import get_settings

STT_URL = "https://api.sarvam.ai/speech-to-text"
TTS_URL = "https://api.sarvam.ai/text-to-speech"

# Languages Sarvam can speak. Anything else is spoken as Indian English.
TTS_LANGUAGES = {"kn-IN", "hi-IN", "en-IN", "ta-IN", "te-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN", "od-IN"}


class SpeechError(Exception):
    pass


@dataclass
class Heard:
    text: str
    language: str
    ms: int


def transcribe(audio: bytes, filename: str = "speech.webm", content_type: str = "audio/webm") -> Heard:
    s = get_settings()
    t0 = time.perf_counter()
    try:
        r = httpx.post(
            STT_URL,
            headers={"api-subscription-key": s.sarvam_api_key},
            files={"file": (filename, audio, content_type)},
            data={"model": s.sarvam_stt_model, "language_code": "unknown", "mode": "codemix"},
            timeout=20,
        )
    except httpx.HTTPError as e:
        raise SpeechError(f"stt {type(e).__name__}") from e
    if r.status_code != 200:
        raise SpeechError(f"stt HTTP {r.status_code}")
    j = r.json()
    return Heard((j.get("transcript") or "").strip(), j.get("language_code") or "kn-IN",
                 int((time.perf_counter() - t0) * 1000))


def speak(text: str, language: str, sample_rate: int | None = None) -> tuple[bytes, int]:
    """WAV audio of `text`, and how long Sarvam took (ms). Phone calls ask for 16000 Hz."""
    s = get_settings()
    lang = language if language in TTS_LANGUAGES else "en-IN"
    t0 = time.perf_counter()
    try:
        r = httpx.post(
            TTS_URL,
            headers={"api-subscription-key": s.sarvam_api_key},
            json={"text": text[:1500], "target_language_code": lang, "model": s.sarvam_tts_model,
                  **({"speech_sample_rate": sample_rate} if sample_rate else {})},
            timeout=20,
        )
    except httpx.HTTPError as e:
        raise SpeechError(f"tts {type(e).__name__}") from e
    if r.status_code != 200:
        raise SpeechError(f"tts HTTP {r.status_code}")
    return _join_wavs([base64.b64decode(a) for a in r.json()["audios"]]), int((time.perf_counter() - t0) * 1000)


def _join_wavs(parts: list[bytes]) -> bytes:
    """Sarvam may return long speech in several WAV pieces: join their audio into one WAV."""
    if len(parts) == 1:
        return parts[0]
    frames, params = [], None
    for p in parts:
        with wave.open(io.BytesIO(p)) as w:
            params = params or w.getparams()
            frames.append(w.readframes(w.getnframes()))
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        w.writeframes(b"".join(frames))
    return out.getvalue()
