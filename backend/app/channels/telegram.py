"""Telegram: citizens message the clerk through a Telegram bot.

Telegram sends each new message to POST /webhooks/telegram. We check it really came from Telegram
(the secret we gave Telegram when registering the webhook comes back in a header), answer "got it"
at once, and do the slow work (download, Sarvam, Gemma, replying) in the background, because
Telegram resends a message whose webhook is slow to answer. A resent message has the same
update_id, so it is noticed and ignored.

What the clerk does with a message is shared with every chat app: see chat.py.
Off (404) until TELEGRAM_BOT_TOKEN is set. Registering the webhook: scripts/telegram_webhook.py.
"""

import hmac
import logging
import threading
from collections import deque

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app import followup
from app.channels.chat import COULD_NOT_FETCH, TOO_LONG, WELCOME, ChatClerk, Incoming
from app.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter(tags=["telegram"])

API = "https://api.telegram.org"
MAX_VOICE_S = 30  # Sarvam hears up to ~30 s in one request
MAX_FILE_BYTES = 5_000_000


clerk = ChatClerk("telegram")
_seen: deque[int] = deque(maxlen=2000)  # recent update_ids, to ignore Telegram's resends
_seen_lock = threading.Lock()


class TelegramError(Exception):
    pass


class TelegramApi:
    """The few Bot API calls we use. The token is part of every address, so addresses are never logged
    and errors carry only the method name and Telegram's own description."""

    def __init__(self, token: str):
        self._token = token

    def _call(self, method: str, **kwargs) -> dict:
        try:
            r = httpx.post(f"{API}/bot{self._token}/{method}", timeout=20, **kwargs)
            body = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise TelegramError(f"{method}: {type(e).__name__}") from None  # no chained error: it holds the URL
        if not body.get("ok"):
            raise TelegramError(f"{method}: {body.get('description', r.status_code)}")
        return body.get("result") or {}

    def download(self, file_id: str) -> bytes:
        path = self._call("getFile", data={"file_id": file_id}).get("file_path")
        if not path:
            raise TelegramError("getFile: no file_path")
        try:
            r = httpx.get(f"{API}/file/bot{self._token}/{path}", timeout=20)
        except httpx.HTTPError as e:
            raise TelegramError(f"download: {type(e).__name__}") from None
        if r.status_code != 200 or len(r.content) > MAX_FILE_BYTES:
            raise TelegramError(f"download: HTTP {r.status_code}, {len(r.content)} bytes")
        return r.content

    def send_text(self, chat_id: str, text: str) -> None:
        self._call("sendMessage", json={"chat_id": chat_id, "text": text[:4096]})

    def send_voice(self, chat_id: str, audio: bytes, mime: str) -> None:
        # Telegram shows MP3 (or OGG/Opus) as a voice note. Anything else goes as an audio file.
        if mime == "audio/mpeg":
            try:
                self._call("sendVoice", data={"chat_id": chat_id}, files={"voice": ("reply.mp3", audio, mime)})
                return
            except TelegramError as e:
                log.warning("sendVoice failed, sending as audio: %s", e)
        name = "reply.mp3" if mime == "audio/mpeg" else "reply.wav"
        self._call("sendAudio", data={"chat_id": chat_id}, files={"audio": (name, audio, mime)})

    def typing(self, chat_id: str) -> None:
        """Shows "typing…" while Gemma thinks (best effort)."""
        try:
            self._call("sendChatAction", json={"chat_id": chat_id, "action": "typing"})
        except TelegramError:
            pass


def ask_fixed(chat_id: str, tracking_number: int, complaint: dict) -> bool:
    """The call-back after a fix, as a Telegram message (app/followup.py). The reply comes back as a
    normal message and chat.py hands it to followup.record_answer."""
    token = get_settings().telegram_bot_token
    if not token:
        return False
    try:
        return clerk.ask_fixed(chat_id, tracking_number, complaint, TelegramApi(token))
    except TelegramError as e:
        log.warning("telegram call-back message failed: %s", e)
        return False


followup.register_chat("telegram", ask_fixed)


def send_update(chat_id: str, text: str) -> None:
    """A status update (app/followup.py notify_update)."""
    token = get_settings().telegram_bot_token
    if token:
        TelegramApi(token).send_text(chat_id, text)


followup.register_notifier("telegram", send_update)


def _first_time(update_id: int) -> bool:
    with _seen_lock:
        if update_id in _seen:
            return False
        _seen.append(update_id)
        return True


@router.post("/webhooks/telegram")
async def webhook(request: Request, background: BackgroundTasks) -> dict:
    s = get_settings()
    if not s.telegram_bot_token:
        raise HTTPException(404, "Not Found")
    given = request.headers.get("x-telegram-bot-api-secret-token", "")
    # No secret configured means nobody can be trusted: refuse everything rather than accept anything.
    if not s.telegram_webhook_secret or not hmac.compare_digest(given.encode(), s.telegram_webhook_secret.encode()):
        raise HTTPException(401, "bad secret")
    try:
        update = await request.json()
    except ValueError:
        raise HTTPException(400, "not json") from None
    update_id = update.get("update_id") if isinstance(update, dict) else None
    message = update.get("message") if isinstance(update, dict) else None
    if isinstance(update_id, int) and isinstance(message, dict) and _first_time(update_id):
        background.add_task(_handle, message, s.telegram_bot_token)
    return {"ok": True}  # anything else (edits, joins, resends) is acknowledged and ignored


def _handle(message: dict, token: str) -> None:
    """One Telegram message, in the background: fetch what it carries and hand it to the clerk."""
    chat = message.get("chat") or {}
    if chat.get("type") != "private" or "id" not in chat:
        return  # the bot only talks one-to-one, never in groups
    chat_id = str(chat["id"])
    api = TelegramApi(token)
    try:
        text = message.get("text") or message.get("caption") or ""
        if text.strip().startswith("/start"):
            api.send_text(chat_id, WELCOME)
            return
        msg = Incoming(text=text)
        try:
            if voice := message.get("voice"):
                if (voice.get("duration") or 0) > MAX_VOICE_S:
                    api.send_text(chat_id, TOO_LONG)
                    return
                msg.audio = (voice.get("mime_type") or "audio/ogg", api.download(voice["file_id"]))
            if photos := message.get("photo"):
                # Telegram sends several sizes, smallest first: take the biggest that isn't huge.
                fits = [p for p in photos if (p.get("file_size") or 0) <= MAX_FILE_BYTES] or photos[:1]
                msg.photo = ("image/jpeg", api.download(fits[-1]["file_id"]))
            elif (doc := message.get("document")) and str(doc.get("mime_type", "")).startswith("image/"):
                # An image sent "as a file": Telegram Desktop always sends .webp this way. CV-1013, 18 Oct:
                # it was silently dropped and only its caption kept.
                msg.photo = (doc["mime_type"], api.download(doc["file_id"]))
        except TelegramError as e:
            log.warning("telegram download failed: %s", e)
            api.send_text(chat_id, COULD_NOT_FETCH)
            return
        if loc := message.get("location"):
            msg.location = (float(loc["latitude"]), float(loc["longitude"]))
        api.typing(chat_id)
        clerk.handle(chat_id, msg, api)
    except Exception:  # one bad message must not take anything else down
        log.exception("telegram message failed")
