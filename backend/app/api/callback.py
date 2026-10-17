"""Vobiz webhooks for the call-back (we rang the citizen; see app/phone/outbound.py).

Each address carries the one-time token made when the call was placed, so only a call we placed
can be answered or streamed here. The stream itself is one-use.
"""

import asyncio
import base64
import json
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from app import events
from app.phone import outbound, vobiz
from app.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/phone/callback", tags=["phone"])

STREAM_GRACE_S = 20  # answered but the stream never came: give up after this long


def _xml(body: str) -> Response:
    return Response(body, media_type="application/xml")


@router.post("/answer/{token}")
async def answer(token: str, request: Request) -> Response:
    sess = outbound.session(token)
    if sess is None or sess.done:
        return _xml(vobiz.reject_xml())
    form = await request.form()
    sess.answered = True
    sess.call_uuid = str(form.get("CallUUID", ""))
    base = get_settings().public_base_url.rstrip("/") or f"https://{request.headers.get('host', 'localhost')}"
    ws = base.replace("https://", "wss://").replace("http://", "ws://") + f"/api/phone/callback/stream/{token}"
    events.publish("callback", tracking_id=f"CV-{sess.tracking_number}", state="answered")
    return _xml(vobiz.stream_xml(ws, base + "/api/phone/stream-status"))


@router.post("/hangup/{token}")
async def hangup(token: str, request: Request) -> dict:
    form = await request.form()
    sess = outbound.session(token)
    if sess is not None and not sess.done:
        if not sess.answered:  # rang out, busy, rejected
            log.info("call-back for CV-%s not answered: %s", sess.tracking_number, form.get("HangupCause"))
            await asyncio.to_thread(sess.finish, "no_answer")
        else:  # the stream is finishing the call; if it never opened, don't wait forever
            asyncio.create_task(_give_up_later(sess))
    return {"ok": True}


async def _give_up_later(sess: outbound.Session) -> None:
    await asyncio.sleep(STREAM_GRACE_S)
    if not sess.done:
        await asyncio.to_thread(sess.finish, "failed")


@router.websocket("/stream/{token}")
async def stream(ws: WebSocket, token: str) -> None:
    sess = outbound.session(token)
    if sess is None or sess.done or not sess.answered:
        await ws.close(code=4403)
        return
    outbound.end_session(token)  # one stream per call
    await ws.accept()

    call: outbound.CallbackCall | None = None
    watchdog: asyncio.Task | None = None
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            event = msg.get("event")
            if event == "start" and call is None:
                start = msg.get("start", {})
                call = outbound.CallbackCall(ws, start.get("streamId", msg.get("streamId", "")),
                                             sess.call_uuid, sess)
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
        if call and call.task and not call.task.done():
            try:  # they answered and hung up straight away: their answer still counts
                await asyncio.wait_for(call.task, timeout=15)
            except Exception:
                pass
        if not sess.done:
            heard_anything = call is not None and call.asks > 0 and call.task is not None
            await asyncio.to_thread(sess.finish, "unclear" if heard_anything else "no_answer")
