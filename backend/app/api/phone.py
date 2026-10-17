"""The phone line: Vobiz calls /answer when someone dials, then streams the call's audio to /stream.

Only a call that came through /answer can open a stream: /answer hands out a one-time
token inside the stream address, so nobody can open a stream directly and spend our
Gemma and Sarvam credits.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from app import events
from app.clerk.clerk import Conversation
from app.contact import seal
from app.db.repo import Repo
from app.phone import vobiz
from app.phone.call import PhoneCall
from app.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/phone", tags=["phone"])

TOKEN_TTL_S = 60  # Vobiz opens the stream within a second or two of /answer
CALLS_PER_HOUR_PER_CALLER = 5

_tokens: dict[str, tuple[str, str, float]] = {}  # token → (call_uuid, caller number, issued)
_calls_by_caller: dict[str, list[float]] = {}
_lock = threading.Lock()


def _xml(body: str) -> Response:
    return Response(body, media_type="application/xml")


def _public_base(request: Request) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return base or f"https://{request.headers.get('host', 'localhost')}"


def caller_identity(number: str) -> tuple[str, str]:
    """Keyed hash (to recognise repeat callers) and last 4 digits (for display). Never the full number."""
    key = get_settings().caller_hash_key.encode()
    digits = "".join(ch for ch in number if ch.isdigit())
    return hmac.new(key, f"phone:{digits}".encode(), hashlib.sha256).hexdigest(), digits[-4:]


@router.post("/answer")
async def answer(request: Request) -> Response:
    form = await request.form()
    call_uuid = str(form.get("CallUUID", ""))
    caller = str(form.get("From", ""))
    if not call_uuid:
        return _xml(vobiz.reject_xml())

    now = time.time()
    with _lock:
        recent = [t for t in _calls_by_caller.get(caller, []) if now - t < 3600]
        if len(recent) >= CALLS_PER_HOUR_PER_CALLER:
            log.warning("rate-limited caller ending %s", caller[-4:])
            return _xml(vobiz.reject_xml())
        _calls_by_caller[caller] = recent + [now]
        for t, (_, _, issued) in list(_tokens.items()):
            if now - issued > TOKEN_TTL_S:
                _tokens.pop(t, None)
        token = secrets.token_urlsafe(24)
        _tokens[token] = (call_uuid, caller, now)

    base = _public_base(request)
    ws = base.replace("https://", "wss://").replace("http://", "ws://") + f"/api/phone/stream/{token}"
    return _xml(vobiz.stream_xml(ws, base + "/api/phone/stream-status"))


@router.post("/hangup")
async def hangup(request: Request) -> dict:
    form = await request.form()
    log.info("call %s ended: %s after %ss", form.get("CallUUID"), form.get("HangupCause"), form.get("Duration"))
    return {"ok": True}


@router.post("/stream-status")
async def stream_status(request: Request) -> dict:
    form = await request.form()
    if form.get("Event") in ("DegradedStream", "DroppedStream"):
        log.warning("stream %s: %s %s", form.get("StreamID"), form.get("Event"), form.get("Error"))
    return {"ok": True}


@router.websocket("/stream/{token}")
async def stream(ws: WebSocket, token: str) -> None:
    with _lock:
        entry = _tokens.pop(token, None)
    if entry is None or time.time() - entry[2] > TOKEN_TTL_S:
        await ws.close(code=4403)
        return
    call_uuid, caller, _ = entry
    await ws.accept()

    call: PhoneCall | None = None
    watchdog: asyncio.Task | None = None
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            event = msg.get("event")
            if event == "start" and call is None:
                start = msg.get("start", {})
                caller_hash, last4 = caller_identity(caller)
                repo = Repo()
                call_id = await asyncio.to_thread(repo.start_call, "phone", caller_hash, call_uuid)
                conv = Conversation(call_id=call_id, repo=repo, channel="phone",
                                    caller_hash=caller_hash, caller_last4=last4, contact_enc=seal("phone", caller))
                call = PhoneCall(ws, start.get("streamId", msg.get("streamId", "")), call_uuid, conv)
                events.publish("call_started", call_id=call_id, channel="phone", caller_last4=last4)
                fmt = start.get("mediaFormat", {})
                if fmt.get("encoding") != "audio/x-l16" or fmt.get("sampleRate") != 16000:
                    log.warning("call %s: unexpected audio format %s", call_uuid, fmt)
                asyncio.create_task(call.start())
                watchdog = asyncio.create_task(call.watchdog())
            elif event == "media" and call is not None:
                call.on_audio(base64.b64decode(msg.get("media", {}).get("payload", "")))
            elif event == "playedStream" and call is not None:
                call.on_played(msg.get("name", ""))
            elif event == "stop":
                break
    except WebSocketDisconnect:
        pass
    finally:
        if watchdog:
            watchdog.cancel()
        if call and not call.finished:
            call.finished = True
            await asyncio.to_thread(call._end, "abandoned", call.conv.state.filed.id if call.conv.state.filed else None)
