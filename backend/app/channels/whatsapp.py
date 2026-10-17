"""WhatsApp: citizens message the clerk on WhatsApp (Meta's WhatsApp Cloud API).

Meta checks the address once (GET: we echo its challenge if it knows our verify token), then sends
every message to POST /webhooks/whatsapp, signed with our app secret (X-Hub-Signature-256: an
HMAC-SHA256 of the exact bytes sent). We check the signature, answer "got it" at once and do the
slow work in the background; Meta resends a message it thinks was missed, with the same message
id, so a resend is noticed and ignored.

What the clerk does with a message is shared with every chat app: see chat.py.
Off (404) until WHATSAPP_ACCESS_TOKEN is set. Checking the token: scripts/whatsapp_check.py.

Meta's 24-hour rule: we may write freely only within 24 h of the citizen's last message; after
that only pre-approved templates. A reply always falls inside it; a later follow-up may not.
"""

import hashlib
import hmac
import json
import logging
import threading
from collections import deque

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app import followup
from app.channels.chat import COULD_NOT_FETCH, TOO_LONG, ChatClerk, Incoming
from app.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter(tags=["whatsapp"])

GRAPH = "https://graph.facebook.com/v25.0"
MAX_FILE_BYTES = 5_000_000
# WhatsApp sends no duration with a voice note. Its voice notes are Opus at about 3 KB a second,
# so this is roughly the 30 s Sarvam can hear in one request.
MAX_VOICE_BYTES = 120_000
FREE_REPLY_WINDOW_S = 24 * 3600  # Meta's 24-hour rule (see above)

clerk = ChatClerk("whatsapp")
_seen: deque[str] = deque(maxlen=2000)  # recent message ids, to ignore Meta's resends
_seen_lock = threading.Lock()


class WhatsAppError(Exception):
    pass


class TooBig(WhatsAppError):
    pass


class WhatsAppApi:
    """The few Graph API calls we use. The access token travels only in the Authorization header;
    errors carry only what was being done and Meta's own message, never the token."""

    def __init__(self, token: str, phone_number_id: str):
        self._headers = {"Authorization": f"Bearer {token}"}
        self._phone = phone_number_id

    def _request(self, what: str, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            r = httpx.request(method, url, headers=self._headers, timeout=20, **kwargs)
        except httpx.HTTPError as e:
            raise WhatsAppError(f"{what}: {type(e).__name__}") from None  # no chained error: it holds the request
        if r.status_code != 200:
            try:
                detail = r.json().get("error", {}).get("message", "")
            except ValueError:
                detail = ""
            raise WhatsAppError(f"{what}: HTTP {r.status_code} {detail}".strip())
        return r

    def download(self, media_id: str, max_bytes: int = MAX_FILE_BYTES) -> tuple[str, bytes]:
        """(mime type, bytes) of a citizen's voice note or photo. Too big raises before downloading."""
        info = self._request("media info", "GET", f"{GRAPH}/{media_id}").json()
        if not info.get("url"):
            raise WhatsAppError("media info: no url")
        if (info.get("file_size") or 0) > max_bytes:
            raise TooBig(media_id)
        # The address expires after 5 minutes and needs the token too.
        data = self._request("media download", "GET", info["url"]).content
        if len(data) > max_bytes:
            raise TooBig(media_id)
        return (info.get("mime_type") or "application/octet-stream").split(";")[0].strip(), data

    def _send(self, to: str, body: dict) -> None:
        self._request("send", "POST", f"{GRAPH}/{self._phone}/messages",
                      json={"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, **body})

    def send_text(self, chat_id: str, text: str) -> None:
        self._send(chat_id, {"type": "text", "text": {"body": text[:4096]}})

    def send_voice(self, chat_id: str, audio: bytes, mime: str) -> None:
        # WhatsApp plays only OGG/Opus as a voice note, which Sarvam can't make; MP3 arrives as an
        # audio message instead (still plays in the chat). WAV it does not accept at all.
        if mime != "audio/mpeg":
            log.warning("whatsapp: no voice reply, %s is not accepted", mime)
            return
        media = self._request("upload", "POST", f"{GRAPH}/{self._phone}/media",
                              data={"messaging_product": "whatsapp", "type": mime},
                              files={"file": ("reply.mp3", audio, mime)}).json()
        self._send(chat_id, {"type": "audio", "audio": {"id": media["id"]}})


def ask_fixed(wa_id: str, tracking_number: int, complaint: dict) -> bool:
    """The call-back after a fix, as a WhatsApp message (app/followup.py) — only inside Meta's 24-hour
    window; outside it the timeline says why (a template message would be needed, not built)."""
    s = get_settings()
    if not s.whatsapp_access_token:
        return False
    try:
        return clerk.ask_fixed(wa_id, tracking_number, complaint, WhatsAppApi(s.whatsapp_access_token,
                               s.whatsapp_phone_number_id), window_s=FREE_REPLY_WINDOW_S)
    except WhatsAppError as e:
        log.warning("whatsapp call-back message failed: %s", e)
        return False


followup.register_chat("whatsapp", ask_fixed)


def _first_time(message_id: str) -> bool:
    with _seen_lock:
        if message_id in _seen:
            return False
        _seen.append(message_id)
        return True


def _same(given: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())


@router.get("/webhooks/whatsapp")
def verify(request: Request) -> PlainTextResponse:
    """Meta's one-time check that this address is ours."""
    s = get_settings()
    if not s.whatsapp_access_token:
        raise HTTPException(404, "Not Found")
    q = request.query_params
    if q.get("hub.mode") != "subscribe" or not _same(q.get("hub.verify_token", ""), s.whatsapp_verify_token):
        raise HTTPException(403, "bad verify token")
    return PlainTextResponse(q.get("hub.challenge", ""))


@router.post("/webhooks/whatsapp")
async def webhook(request: Request, background: BackgroundTasks) -> dict:
    s = get_settings()
    if not s.whatsapp_access_token:
        raise HTTPException(404, "Not Found")
    raw = await request.body()
    # The signature covers the exact bytes Meta sent, so it is checked before anything is parsed.
    # No app secret configured means nobody can be trusted: refuse everything.
    expected = ""
    if s.whatsapp_app_secret:
        expected = "sha256=" + hmac.new(s.whatsapp_app_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not _same(request.headers.get("x-hub-signature-256", ""), expected):
        raise HTTPException(401, "bad signature")
    try:
        update = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "not json") from None
    for message in _messages(update, s.whatsapp_phone_number_id):
        if isinstance(message.get("id"), str) and _first_time(message["id"]):
            background.add_task(_handle, message, s.whatsapp_access_token, s.whatsapp_phone_number_id)
    return {"ok": True}  # delivery receipts ("statuses") and anything else are acknowledged and ignored


def _messages(update, phone_number_id: str) -> list[dict]:
    """The citizens' messages in one webhook call, only those sent to OUR number."""
    out = []
    for entry in (update.get("entry") or []) if isinstance(update, dict) else []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            if (value.get("metadata") or {}).get("phone_number_id") != phone_number_id:
                continue
            out += [m for m in value.get("messages") or [] if isinstance(m, dict) and m.get("from")]
    return out


def _handle(message: dict, token: str, phone_number_id: str) -> None:
    """One WhatsApp message, in the background: fetch what it carries and hand it to the clerk."""
    wa_id = str(message["from"])
    api = WhatsAppApi(token, phone_number_id)
    kind = message.get("type")
    try:
        msg = Incoming()
        try:
            if kind == "text":
                msg.text = (message.get("text") or {}).get("body") or ""
            elif kind == "audio":
                msg.audio = api.download(message["audio"]["id"], MAX_VOICE_BYTES)
            elif kind == "image":
                msg.photo = api.download(message["image"]["id"])
                msg.text = message["image"].get("caption") or ""
            elif kind == "location":
                loc = message["location"]
                msg.location = (float(loc["latitude"]), float(loc["longitude"]))
        except WhatsAppError as e:
            log.warning("whatsapp download failed: %s", e)
            api.send_text(wa_id, TOO_LONG if isinstance(e, TooBig) and kind == "audio" else COULD_NOT_FETCH)
            return
        clerk.handle(wa_id, msg, api)  # anything else (stickers, documents…) gets "please send text…"
    except Exception:  # one bad message must not take anything else down
        log.exception("whatsapp message failed")
