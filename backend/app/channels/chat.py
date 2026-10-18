"""One chat with the clerk, for messaging apps: Telegram and WhatsApp.

A messaging app hands over what the citizen sent (words, a voice note, a photo, a location pin)
as an `Incoming`, plus a `Messenger` that knows how to send things back on that app. Everything
else is the same for every chat app and lives here: one clerk Conversation per chat, kept in
memory until the chat goes quiet; voice notes heard by Sarvam and answered in voice; photos looked
at by Gemma and kept with the complaint; a location pin used as the place.

Chats live in memory on this one server, like the try-it page (fine for a single instance).
"""

import hashlib
import hmac
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Protocol

from app import contact, events, followup, vision
from app.clerk.clerk import Conversation
from app.clerk.language import guess_language
from app.db import repo as db
from app.db.models import CATEGORIES
from app.db.repo import Repo, save_turn
from app.places import gazetteer, maps_link
from app.settings import get_settings
from app.speech import sarvam
from app.tools.clerk_tools import OfferedPlace, spoken_id

log = logging.getLogger(__name__)

CHAT_TTL_S = 30 * 60  # a chat quiet this long starts afresh
MAX_CHATS = 500
RATE_LIMIT_MESSAGES = 20  # per chat …
RATE_LIMIT_WINDOW_S = 10 * 60  # … per 10 minutes
MAX_PHOTOS = 3  # per complaint
PHOTO_AFTER_FILING_S = 10 * 60  # a photo this soon after filing belongs to that complaint
PIN_MAX_KM = 15  # a pin farther than this from every known place is outside Bengaluru
AWAIT_ANSWER_S = 3 * 24 * 3600  # an unanswered "is it really fixed?" is forgotten after 3 days

# Fixed messages, in the three languages the greeting offers.
WELCOME = ("ನಮಸ್ಕಾರ, Citizen's Voice ಗೆ ಸ್ವಾಗತ. ನಿಮ್ಮ ಏರಿಯಾದ problem ಬಗ್ಗೆ type ಮಾಡಿ ಅಥವಾ voice message ಕಳಿಸಿ.\n"
           "नमस्ते! अपने इलाके की problem लिखिए या voice message भेजिए।\n"
           "Hello! Tell me about a problem in your area: type it or send a voice note. "
           "You can also send a photo, your location, or a Google Maps link to the exact spot.")
BUSY = "ತುಂಬಾ messages ಬಂದಿವೆ, ಸ್ವಲ್ಪ ಹೊತ್ತು ಬಿಟ್ಟು ಕಳಿಸಿ. / Too many messages: please try again in a few minutes."
NOT_HEARD = "ಕ್ಷಮಿಸಿ, ಕೇಳಿಸಲಿಲ್ಲ. ಮತ್ತೆ ಕಳಿಸ್ತೀರಾ? / Sorry, I couldn't hear that. Could you send it again?"
HOW_TO = ("ದಯವಿಟ್ಟು text, voice message, photo ಅಥವಾ location ಕಳಿಸಿ. / "
          "Please send text, a voice note, a photo or your location.")
PHOTO_ADDED = ("ನಿಮ್ಮ photo {tid} complaint ಗೆ ಸೇರಿಸಲಾಗಿದೆ. / Your photo was added to complaint {tid}. "
               "If it shows a different problem, tell me about it.")
TOO_LONG = ("ದಯವಿಟ್ಟು 30 seconds ಒಳಗಿನ voice message ಕಳಿಸಿ. / "
            "Please keep voice notes under 30 seconds.")
COULD_NOT_FETCH = "ಕ್ಷಮಿಸಿ, ಅದನ್ನು ತೆರೆಯಲು ಆಗಲಿಲ್ಲ. / Sorry, I couldn't open that. Could you send it again?"
# After an officer marks a complaint fixed: the citizen's own answer decides (app/followup.py).
FIXED_QUESTION = {
    "kn": "ನಿಮ್ಮ complaint {tid} ({summary}) fix ಆಗಿದೆ ಅಂತ officer ಹೇಳಿದ್ದಾರೆ. ನಿಜವಾಗ್ಲೂ fix ಆಗಿದ್ಯಾ? "
          "ಹೌದು ಅಥವಾ ಇಲ್ಲ ಅಂತ reply ಮಾಡಿ.",
    "hi": "आपकी complaint {tid} ({summary}) को officer ने fixed बताया है। क्या सच में ठीक हो गया? "
          "हाँ या नहीं में जवाब दीजिए।",
    "en": "The officer says your complaint {tid} ({summary}) is fixed. Is it really fixed? Please reply yes or no.",
}
THANKS = {
    "yes": "ಧನ್ಯವಾದಗಳು! {tid} fix ಆಗಿದೆ ಅಂತ ದಾಖಲಿಸಿದ್ದೀವಿ. / Thank you! {tid} is recorded as fixed.",
    "no": "ಕ್ಷಮಿಸಿ. {tid} ಮತ್ತೆ open ಮಾಡಿದ್ದೀವಿ, priority ಹೆಚ್ಚಿಸಿದ್ದೀವಿ. / Sorry. {tid} is reopened with a higher priority.",
}


@dataclass
class Incoming:
    """What a citizen sent in one message. A message can carry several (a photo with a caption)."""

    text: str = ""
    audio: tuple[str, bytes] | None = None  # (mime type, bytes): a voice note
    photo: tuple[str, bytes] | None = None  # (mime type, bytes)
    location: tuple[float, float] | None = None  # (lat, lon) of a location pin


class Messenger(Protocol):
    """Sends back on one chat app. Telegram's is in telegram.py; WhatsApp's will be its own."""

    def send_text(self, chat_id: str, text: str) -> None: ...

    def send_voice(self, chat_id: str, audio: bytes, mime: str) -> None: ...


@dataclass
class Chat:
    conv: Conversation | None = None  # None until the citizen's next message after a filing
    last: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)  # one message at a time per chat
    photos: list[tuple[str, bytes, dict | None]] = field(default_factory=list)  # kept until filing
    filed: tuple[int, float] | None = None  # (tracking number, when) of this chat's latest complaint


class ChatClerk:
    """Every chat on one app (channel), each with its own conversation with the clerk."""

    def __init__(self, channel: str):
        self.channel = channel
        self._chats: dict[str, Chat] = {}
        self._times: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._seen_at: dict[str, float] = {}  # when each chat last wrote to us (WhatsApp's 24-hour rule)
        self._awaiting: dict[str, tuple[int, str, float]] = {}  # chat → (tracking number, language, asked at)

    def handle(self, chat_id: str, msg: Incoming, out: Messenger) -> None:
        """One message from a citizen. Runs in the background: slow work is fine here."""
        with self._lock:
            self._seen_at[chat_id] = time.time()
        if self._rate_limited(chat_id):
            out.send_text(chat_id, BUSY)
            return
        chat = self._chat(chat_id)
        with chat.lock:
            try:
                self._handle(chat, chat_id, msg, out)
            finally:
                chat.last = time.time()

    def _handle(self, chat: Chat, chat_id: str, msg: Incoming, out: Messenger) -> None:
        words, language, stt_ms, by_voice = msg.text.strip()[:1000], None, 0, False
        if msg.audio:
            mime, data = msg.audio
            try:
                heard = sarvam.transcribe(data, "voice.ogg", mime)
            except sarvam.SpeechError as e:
                log.warning("%s stt failed: %s", self.channel, e)
                heard = None
            if not (heard and heard.text):
                out.send_text(chat_id, NOT_HEARD)
                return
            words, language, stt_ms, by_voice = heard.text, heard.language, heard.ms, True
        elif words:
            language = guess_language(words)

        if words and self._answered_fixed_question(chat_id, words, language, out):
            return
        if not (words or msg.photo or msg.location):  # a sticker, a file, a contact card…
            out.send_text(chat_id, HOW_TO)
            return
        if msg.photo and not words and not msg.location and self._recently_filed(chat):
            # A photo right after filing, before anything new: it shows the complaint just filed.
            number = chat.filed[0]
            self._store_photo(number, msg.photo, self._look(msg.photo))
            out.send_text(chat_id, PHOTO_ADDED.format(tid=f"CV-{number}"))
            return

        if chat.conv is None:
            chat.conv = self._new_conversation(chat_id)
            chat.photos.clear()
        notes = []
        if msg.location:
            notes.append(self._pin(chat.conv, *msg.location))
        elif words:
            words, link_note = with_maps_link(chat.conv, words)
            if link_note:
                notes.append(link_note)
        if msg.photo:
            notes.append(self._photo(chat, msg.photo))

        conv = chat.conv
        caller_text = " ".join([words] + notes).strip()
        result = conv.turn(caller_text, language)
        out.send_text(chat_id, _written(result.reply, conv))
        if by_voice:  # answered in the same way they asked: a voice note gets a voice reply too
            voice = self._voice(result.reply, result.language)
            if voice:
                out.send_voice(chat_id, *voice)
        save_turn(conv, caller_text, stt_ms, result)

        if result.complaint:
            number = conv.state.filed.tracking_number
            for mime, data, verdict in chat.photos:
                self._store_photo(number, (mime, data), verdict)
            chat.filed = (number, time.time())
        if result.complaint or result.ended:
            chat.conv = None  # one complaint per conversation: the next message starts a new one
            chat.photos.clear()

    def ask_fixed(self, chat_id: str, tracking_number: int, complaint: dict, out: Messenger,
                  window_s: float | None = None) -> bool:
        """Send "is it really fixed?" (followup.register_chat). False if it could not be sent.
        window_s: only if the citizen wrote to us that recently (WhatsApp allows 24 h); otherwise noted."""
        tid = f"CV-{tracking_number}"
        if window_s is not None:
            with self._lock:
                seen = self._seen_at.get(chat_id)
            if seen is None or time.time() - seen > window_s:
                db.add_note(tracking_number, f"call-back: not sent on {self.channel} — it allows messages only within "
                                             f"{window_s / 3600:.0f} h of the citizen's last message; they can confirm "
                                             "by calling the helpline")
                return False
        lang = (complaint.get("language") or "kn-IN").split("-")[0]
        summary = (complaint.get("summary_local") if lang != "en" else None) or complaint.get("summary_en") or ""
        out.send_text(chat_id, FIXED_QUESTION.get(lang, FIXED_QUESTION["en"]).format(tid=tid, summary=summary[:120]))
        with self._lock:
            now = time.time()
            for cid, (_, _, at) in list(self._awaiting.items()):
                if now - at > AWAIT_ANSWER_S:
                    self._awaiting.pop(cid, None)
            self._awaiting[chat_id] = (tracking_number, complaint.get("language") or "kn-IN", now)
        return True

    def _answered_fixed_question(self, chat_id: str, words: str, language: str | None, out: Messenger) -> bool:
        """The citizen's reply to "is it really fixed?". True if it was a clear yes or no (handled here);
        anything else is recorded as unclear and the message goes on to the clerk as usual."""
        with self._lock:
            waiting = self._awaiting.pop(chat_id, None)
        if waiting is None:
            return False
        number, asked_in, _ = waiting
        answer = followup.classify(words, language or asked_in)
        followup.record_answer(number, answer, words, channel=self.channel)
        if answer in THANKS:
            out.send_text(chat_id, THANKS[answer].format(tid=f"CV-{number}"))
            return True
        return False

    def _new_conversation(self, chat_id: str) -> Conversation:
        repo = Repo()
        key = get_settings().caller_hash_key.encode()
        caller_hash = hmac.new(key, f"{self.channel}:{chat_id}".encode(), hashlib.sha256).hexdigest()
        call_id = repo.start_call(self.channel, caller_hash=caller_hash)
        events.publish("call_started", call_id=call_id, channel=self.channel, greeting="")
        # The chat id, encrypted, so the "is it really fixed?" follow-up can message them later.
        return Conversation(call_id=call_id, repo=repo, channel=self.channel, caller_hash=caller_hash,
                            contact_enc=contact.seal(self.channel, chat_id), written=True)

    def _pin(self, conv: Conversation, lat: float, lon: float) -> str:
        return pin_note(conv, lat, lon)

    def _photo(self, chat: Chat, photo: tuple[str, bytes]) -> str:
        """Gemma looks at the photo; the clerk is told what it shows; it waits for the filing."""
        verdict = self._look(photo)
        if len(chat.photos) < MAX_PHOTOS:
            chat.photos.append((*photo, verdict))
        if not verdict or verdict.get("error"):
            return "[The citizen sent a photo of the problem. It will be attached to the complaint.]"
        if verdict.get("is_civic_problem") is False:
            return (f"[The citizen sent a photo. It shows: {verdict.get('what_i_see', '')} — it does not seem to "
                    "show a civic problem. Ask what problem they want to report.]")
        return (f"[The citizen sent a photo. It shows: {verdict.get('what_i_see', '')} (looks like "
                f"{verdict.get('category', 'unknown')}, severity {verdict.get('severity', '?')} of 5). It will be "
                "attached to the complaint; don't ask them to describe what the photo already shows.]")

    @staticmethod
    def _look(photo: tuple[str, bytes]) -> dict | None:
        if not get_settings().feature_photo_check:
            return None
        return vision.look_at_problem(photo, list(CATEGORIES))

    def _store_photo(self, number: int, photo: tuple[str, bytes], verdict: dict | None) -> None:
        try:  # a photo that can't be saved must not cost the citizen their reply
            db.add_photo(number, "citizen", photo[0], photo[1], verdict)
        except Exception:
            log.exception("could not save %s photo for CV-%s", self.channel, number)

    @staticmethod
    def _voice(text: str, language: str) -> tuple[bytes, str] | None:
        try:
            audio, _ = sarvam.speak(text, language, codec="mp3")
        except sarvam.SpeechError as e:
            log.warning("tts failed: %s", e)
            return None  # the text reply has already gone
        return audio, "audio/wav" if audio[:4] == b"RIFF" else "audio/mpeg"

    def _recently_filed(self, chat: Chat) -> bool:
        fresh = chat.conv is None or chat.conv.state.caller_turn == 0
        return fresh and chat.filed is not None and time.time() - chat.filed[1] < PHOTO_AFTER_FILING_S

    def _chat(self, chat_id: str) -> Chat:
        now = time.time()
        with self._lock:
            for cid, c in list(self._chats.items()):
                if now - c.last > CHAT_TTL_S and not c.lock.locked():
                    self._chats.pop(cid, None)
            while len(self._chats) >= MAX_CHATS:
                self._chats.pop(min(self._chats, key=lambda k: self._chats[k].last), None)
            return self._chats.setdefault(chat_id, Chat())

    def _rate_limited(self, chat_id: str) -> bool:
        now = time.time()
        with self._lock:
            recent = [t for t in self._times.get(chat_id, []) if now - t < RATE_LIMIT_WINDOW_S]
            limited = len(recent) >= RATE_LIMIT_MESSAGES
            if not limited:
                recent.append(now)
            self._times[chat_id] = recent
            return limited

    def clear(self) -> None:
        """Forget every chat (tests)."""
        with self._lock:
            self._chats.clear()
            self._times.clear()
            self._seen_at.clear()
            self._awaiting.clear()


def pin_note(conv: Conversation, lat: float, lon: float, what: str = "location pin") -> str:
    """A location pin (or a Google Maps link) becomes a place the clerk may file at, without asking where."""
    near, km = _nearest_place(lat, lon)
    if near is None or km > PIN_MAX_KM:
        return (f"[The citizen shared a {what}, but it is outside Bengaluru. Tell them we only take "
                "complaints in Bengaluru.]")
    label = f"Location pin near {near.label}" if km <= 2 else f"Location pin ({lat:.5f}, {lon:.5f})"
    pid = f"pin:{lat:.5f},{lon:.5f}"
    place = gazetteer.Place(pid, label, "", "pin", round(lat, 6), round(lon, 6), near.area)
    # Offered as of the turn BEFORE this one: the citizen chose the place by pinning it, so it
    # counts as confirmed and the complaint can be filed there without a read-back of the place.
    conv.state.offered[pid] = OfferedPlace(place, conv.state.caller_turn)
    return (f"[The citizen shared their {what}: {label} [{pid}]. Use it as the place of the problem: "
            "do not ask where it is and do not call find_place for it.]")


def with_maps_link(conv: Conversation, words: str) -> tuple[str, str | None]:
    """A Google Maps link in the citizen's words (18 Oct: for a precise spot in chats and the browser):
    the words without the link, and a note for the clerk (the pin, or that the link couldn't be read)."""
    link = maps_link.find(words)
    if not link:
        return words, None
    rest = " ".join(words.replace(link, " ").split())
    spot = maps_link.location(link)
    if spot is None:
        return rest, ("[The citizen sent a Google Maps link, but it could not be read. Ask them for a nearby "
                      "landmark, or (in a chat) to send their location pin.]")
    return rest, pin_note(conv, *spot, what="Google Maps link")


def _written(reply: str, conv: Conversation) -> str:
    """The clerk says a tracking ID for the ear ("C V, 1 0, 4 2"); in a chat it reads "CV-1042"."""
    if conv.state.filed is None:
        return reply
    number = conv.state.filed.tracking_number
    return reply.replace(spoken_id(number), f"CV-{number}")


def _nearest_place(lat: float, lon: float) -> tuple[gazetteer.Place | None, float]:
    best, best_km = None, float("inf")
    for p in gazetteer.load():
        km = gazetteer.km_between(lat, lon, p.lat, p.lon)
        if km < best_km:
            best, best_km = p, km
    return best, best_km
