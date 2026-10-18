"""Sarvam: the ears (speech → text) and the mouth (text → speech), plus translating an officer's note
into the citizen's language. It makes no decisions."""

import base64
import io
import logging
import time
import wave
from dataclasses import dataclass

import httpx

from app.settings import get_settings

log = logging.getLogger(__name__)

STT_URL = "https://api.sarvam.ai/speech-to-text"
TTS_URL = "https://api.sarvam.ai/text-to-speech"
TRANSLATE_URL = "https://api.sarvam.ai/translate"
TRANSLATE_TIMEOUT_S = 8  # a status update waits on it: better the original note than a late one

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


def speak(text: str, language: str, sample_rate: int | None = None, codec: str | None = None) -> tuple[bytes, int]:
    """Audio of `text` (WAV unless another codec is asked for), and how long Sarvam took (ms).
    Phone calls ask for 16000 Hz; chat apps ask for "mp3", which Telegram plays as a voice note."""
    s = get_settings()
    lang = language if language in TTS_LANGUAGES else "en-IN"
    t0 = time.perf_counter()
    try:
        r = httpx.post(
            TTS_URL,
            headers={"api-subscription-key": s.sarvam_api_key},
            json={"text": text[:1500], "target_language_code": lang, "model": s.sarvam_tts_model,
                  "speaker": s.sarvam_tts_speaker, "pace": s.sarvam_tts_pace,
                  "temperature": s.sarvam_tts_temperature,
                  **({"speech_sample_rate": sample_rate} if sample_rate else {}),
                  **({"output_audio_codec": codec} if codec else {})},
            timeout=20,
        )
    except httpx.HTTPError as e:
        raise SpeechError(f"tts {type(e).__name__}") from e
    if r.status_code != 200:
        raise SpeechError(f"tts HTTP {r.status_code}")
    parts = [base64.b64decode(a) for a in r.json()["audios"]]
    ms = int((time.perf_counter() - t0) * 1000)
    if codec and codec != "wav":
        return b"".join(parts), ms  # MP3 pieces play correctly simply laid end to end
    return join_wavs(parts), ms


def translate(text: str, target_language: str) -> str | None:
    """`text` in `target_language` ("kn-IN", "hi-IN", …), or None if Sarvam couldn't: the caller then
    sends the original. Never raises."""
    s = get_settings()
    if not s.sarvam_api_key:
        return None
    try:
        r = httpx.post(
            TRANSLATE_URL,
            headers={"api-subscription-key": s.sarvam_api_key},
            json={"input": text[:1000], "source_language_code": "auto", "target_language_code": target_language,
                  "model": s.sarvam_translate_model},
            timeout=TRANSLATE_TIMEOUT_S,
        )
        if r.status_code != 200:
            log.warning("translate HTTP %s", r.status_code)
            return None
        out = r.json().get("translated_text")
    except Exception as e:  # timeout, bad JSON, a reply that isn't an object: all mean "no translation"
        log.warning("translate failed: %s", type(e).__name__)
        return None
    if not isinstance(out, str) or not out.strip():
        log.warning("translate: no translated_text in the reply")
        return None
    return out.strip()


def join_wavs(parts: list[bytes]) -> bytes:
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
