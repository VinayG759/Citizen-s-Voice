"""The try-it page: anyone (judges included) talks to the clerk from a browser.

Same clerk as the phone line. Conversations live in memory on this one server
(fine for a single instance; noted in the README) and every turn is also saved
to the database so the dashboard can show it.
"""

import base64
import hashlib
import hmac
import logging
import threading
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

import re

from pydantic import BaseModel

from app import events
from app.contact import seal
from app.clerk.clerk import Conversation
from app.clerk.language import guess_language, written_in
from app.phone.call import GREETING as GREETING_PARTS, greeting_text
from app.db.repo import Repo, save_turn
from app.settings import get_settings
from app.speech import sarvam

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/try", tags=["try-it"])

MAX_AUDIO_BYTES = 2_000_000  # ~2 minutes of browser Opus; a 30 s turn is far smaller
SESSION_TTL_S = 30 * 60
MAX_SESSIONS = 300
RATE_LIMIT_TURNS = 20  # per visitor IP …
RATE_LIMIT_WINDOW_S = 10 * 60  # … per 10 minutes

# The same greeting as the phone line (one copy, so they can't drift apart).
GREETING = {"text": greeting_text(), "language": "kn-IN"}

_sessions: dict[str, tuple[Conversation, float]] = {}
_turn_times: dict[str, list[float]] = {}
_spoken: dict[str, tuple[int, int]] = {}  # session → (index of reply voiced, times voiced)
MAX_PLAYS_PER_REPLY = 2
_lock = threading.Lock()
_greeting_audio: str | None = None


def _client_ip(request: Request) -> str:
    # On Railway every request comes from its proxy, which overwrites X-Real-IP with the visitor's address
    # (a visitor's own copy is replaced). Without it (the laptop) the connection's address is used.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def _rate_limited(ip: str) -> bool:
    now = time.time()
    with _lock:
        recent = [t for t in _turn_times.get(ip, []) if now - t < RATE_LIMIT_WINDOW_S]
        limited = len(recent) >= RATE_LIMIT_TURNS
        if not limited:
            recent.append(now)
        _turn_times[ip] = recent
        return limited


def _prune() -> None:
    now = time.time()
    for sid, (_, last) in list(_sessions.items()):
        if now - last > SESSION_TTL_S:
            _sessions.pop(sid, None)
    while len(_sessions) > MAX_SESSIONS:
        _sessions.pop(min(_sessions, key=lambda k: _sessions[k][1]), None)


def _greeting_b64() -> str | None:
    """Each language of the greeting in its own voice settings, joined into one recording."""
    try:
        wav = sarvam.join_wavs([sarvam.speak(text, lang)[0] for text, lang in GREETING_PARTS])
        return base64.b64encode(wav).decode()
    except sarvam.SpeechError as e:
        log.warning("greeting tts failed: %s", e)
        return None  # the page still shows the text


def _speak_b64(text: str, language: str) -> tuple[str | None, int]:
    try:
        audio, ms = sarvam.speak(text, language)
        return base64.b64encode(audio).decode(), ms
    except sarvam.SpeechError as e:
        log.warning("tts failed: %s", e)
        return None, 0  # the page still shows the text


@router.post("/start")
def start() -> dict:
    global _greeting_audio
    sid = uuid.uuid4().hex
    repo = Repo()
    key = get_settings().caller_hash_key.encode()
    caller_hash = hmac.new(key, f"web:{sid}".encode(), hashlib.sha256).hexdigest()
    call_id = repo.start_call("web", caller_hash=caller_hash)
    with _lock:
        _prune()
        _sessions[sid] = (Conversation(call_id=call_id, repo=repo, channel="web", caller_hash=caller_hash), time.time())
    events.publish("call_started", call_id=call_id, channel="web", greeting=GREETING["text"])
    if _greeting_audio is None:
        _greeting_audio = _greeting_b64()
    return {"session_id": sid, "greeting": GREETING["text"], "greeting_audio": _greeting_audio}


@router.post("/turn")
def turn(
    request: Request,
    background: BackgroundTasks,
    session_id: str = Form(...),
    text: str | None = Form(None),
    audio: UploadFile | None = File(None),
) -> dict:
    with _lock:
        entry = _sessions.get(session_id)
    if entry is None:
        raise HTTPException(404, "session expired")
    conv = entry[0]
    if _rate_limited(_client_ip(request)):
        raise HTTPException(429, "too many turns")

    stt_ms = 0
    language = None
    if audio is not None:
        data = audio.file.read(MAX_AUDIO_BYTES + 1)
        if len(data) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "recording too long")
        if len(data) < 1000:
            raise HTTPException(422, "recording too short")
        try:
            heard = sarvam.transcribe(data, audio.filename or "speech.webm", audio.content_type or "audio/webm")
        except sarvam.SpeechError as e:
            log.warning("stt failed: %s", e)
            raise HTTPException(502, "could not hear") from e
        caller_text, language, stt_ms = heard.text, heard.language, heard.ms
    else:
        caller_text = (text or "").strip()[:1000]
        language = guess_language(caller_text)
    if not caller_text:
        raise HTTPException(422, "nothing heard")

    result = conv.turn(caller_text, language)
    with _lock:
        _sessions[session_id] = (conv, time.time())
    # The reply goes back now; its voice is fetched separately (/speak) and history is saved after.
    background.add_task(save_turn, conv, caller_text, stt_ms, result)

    return {
        "caller_text": caller_text,
        "language": result.language,
        "reply": result.reply,
        "events": result.events,
        "complaint": result.complaint,
        "ended": result.ended,
        "timings": {"stt_ms": stt_ms, "llm_ms": result.llm_ms},
    }


class CallbackNumber(BaseModel):
    session_id: str
    phone: str


_INDIAN_MOBILE = re.compile(r"(?:\+?91|0)?([6-9]\d{9})")


@router.post("/contact")
def leave_number(body: CallbackNumber, request: Request) -> dict:
    """After filing in the browser: an optional mobile number, so we can call back when it's fixed.
    Stored encrypted like a phone caller's; only the last 4 digits are ever shown."""
    with _lock:
        entry = _sessions.get(body.session_id)
    if entry is None:
        raise HTTPException(404, "session expired")
    conv = entry[0]
    if conv.state.filed is None:
        raise HTTPException(409, "file the complaint first")
    if _rate_limited(_client_ip(request)):
        raise HTTPException(429, "too many requests")
    m = _INDIAN_MOBILE.fullmatch(re.sub(r"[\s-]", "", body.phone))
    if not m:
        raise HTTPException(422, "enter a 10-digit Indian mobile number")
    sealed = seal("phone", f"+91{m.group(1)}")
    if sealed is None:
        raise HTTPException(503, "call-backs are not set up on this server")
    if not conv.repo.set_contact(conv.state.filed.id, sealed, m.group(1)[-4:]):
        raise HTTPException(409, "this report keeps no contact details")
    return {"ok": True, "last4": m.group(1)[-4:]}


@router.post("/speak")
def speak(session_id: str = Form(...)) -> Response:
    """The voice of the clerk's latest reply in this conversation — never arbitrary text."""
    with _lock:
        entry = _sessions.get(session_id)
    if entry is None:
        raise HTTPException(404, "session expired")
    conv = entry[0]
    index = next((i for i in range(len(conv.messages) - 1, -1, -1)
                  if conv.messages[i].role == "model" and conv.messages[i].text), None)
    if index is None:
        raise HTTPException(404, "nothing to say")
    last = conv.messages[index]
    with _lock:
        seen_index, plays = _spoken.get(session_id, (-1, 0))
        plays = plays + 1 if seen_index == index else 1
        if plays > MAX_PLAYS_PER_REPLY:
            raise HTTPException(429, "already spoken")
        _spoken[session_id] = (index, plays)
    try:
        audio, ms = sarvam.speak(last.text, written_in(last.text, conv.language))
    except sarvam.SpeechError as e:
        log.warning("tts failed: %s", e)
        raise HTTPException(502, "could not speak") from e
    return Response(audio, media_type="audio/wav", headers={"X-TTS-Ms": str(ms), "Cache-Control": "no-store"})
