"""Sarvam: the ears (speech → text) and the mouth (text → speech). Nothing else."""

import base64
import time
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


def speak(text: str, language: str) -> tuple[bytes, int]:
    """WAV audio of `text`, and how long Sarvam took (ms)."""
    s = get_settings()
    lang = language if language in TTS_LANGUAGES else "en-IN"
    t0 = time.perf_counter()
    try:
        r = httpx.post(
            TTS_URL,
            headers={"api-subscription-key": s.sarvam_api_key},
            json={"text": text[:1500], "target_language_code": lang, "model": s.sarvam_tts_model},
            timeout=20,
        )
    except httpx.HTTPError as e:
        raise SpeechError(f"tts {type(e).__name__}") from e
    if r.status_code != 200:
        raise SpeechError(f"tts HTTP {r.status_code}")
    audio = base64.b64decode("".join(r.json()["audios"]))
    return audio, int((time.perf_counter() - t0) * 1000)
