"""The call-back: we ring the citizen after an officer marks their complaint fixed.

A short scripted exchange, not a conversation: we say which complaint and that the office says it
is fixed, ask "is it really fixed?", listen to one answer (twice at most if we couldn't tell),
say a closing line and hang up. What their answer means is decided in app/followup.py.

The audio path is the same as an incoming call (Vobiz streams the call over a WebSocket, 16 kHz);
only the start differs: we ask Vobiz to place the call, and Vobiz fetches our answer address
when the citizen picks up.
"""

import asyncio
import base64
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx

from app.phone import audio, vobiz
from app.settings import get_settings
from app.speech import sarvam

log = logging.getLogger(__name__)

SESSION_TTL_S = 10 * 60  # ringing + the exchange; anything older is forgotten
RING_TIMEOUT_S = 40
ANSWER_SILENCE_MS = 1200
WAIT_FOR_ANSWER_S = 10  # silence after the question → ask once more, then give up
MAX_ASKS = 2
MAX_CALL_S = 2 * 60

# Written the way people SAY them (see phone/call.py). {complaint} is "C V 1 0 0 4" so the voice reads
# each digit; {summary} is the complaint in a few words.
QUESTION = {
    "kn-IN": "ನಮಸ್ಕಾರ, ನಾನು Citizen's Voice ಇಂದ call ಮಾಡ್ತಿದ್ದೀನಿ, ನಿಮ್ಮ complaint {complaint} ಬಗ್ಗೆ: {summary}. "
             "Office ಅವರು ಇದು ಸರಿ ಆಗಿದೆ ಅಂತ ಹೇಳ್ತಿದ್ದಾರೆ. ನಿಜವಾಗ್ಲೂ ಸರಿ ಆಗಿದ್ಯಾ?",
    "hi-IN": "नमस्ते, मैं Citizen's Voice से बोल रही हूँ, आपकी complaint {complaint} के बारे में: {summary}. "
             "Office का कहना है कि यह ठीक हो गया है. क्या सच में ठीक हो गया है?",
    "en-IN": "Hello, this is Citizen's Voice about your complaint {complaint}: {summary}. "
             "The office says it is fixed. Is it really fixed?",
}
LINES = {
    "again": {
        "kn-IN": "ಕ್ಷಮಿಸಿ, ಸರಿಯಾಗಿ ಕೇಳಿಸ್ಲಿಲ್ಲ. ಸರಿ ಆಗಿದ್ಯಾ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಅಂತ ಹೇಳಿ.",
        "hi-IN": "माफ़ कीजिए, ठीक से सुनाई नहीं दिया. क्या ठीक हो गया है? हाँ या नहीं बताइए.",
        "en-IN": "Sorry, I didn't catch that. Is it fixed? Please say yes or no.",
    },
    "yes": {
        "kn-IN": "ಧನ್ಯವಾದಗಳು, ನಿಮ್ಮ ಮಾತು ದಾಖಲಿಸಿಕೊಂಡೆ. ನಮಸ್ಕಾರ.",
        "hi-IN": "बताने के लिए धन्यवाद. नमस्ते.",
        "en-IN": "Thank you for confirming. Goodbye.",
    },
    "no": {
        "kn-IN": "ಕ್ಷಮಿಸಿ. ನಿಮ್ಮ complaint ಮತ್ತೆ open ಮಾಡಿ, office ಅವರಿಗೆ ತಿಳಿಸಿದ್ದೀನಿ. ನಮಸ್ಕಾರ.",
        "hi-IN": "माफ़ कीजिए. आपकी complaint फिर से खोल दी है और office को बता दिया है. नमस्ते.",
        "en-IN": "Sorry about that. I have reopened your complaint and told the office. Goodbye.",
    },
    "unclear": {
        "kn-IN": "ಸರಿ. ಏನಾದ್ರೂ ಹೇಳಬೇಕಾದ್ರೆ ಇದೇ number ಗೆ call ಮಾಡಿ. ಧನ್ಯವಾದಗಳು.",
        "hi-IN": "ठीक है. कुछ बताना हो तो इसी number पर call कीजिए. धन्यवाद.",
        "en-IN": "Alright. If you want to tell us, call this number any time. Thank you.",
    },
}


def spoken_id(tracking_number: int) -> str:
    """1004 → "C V 1 0 0 4": read letter by letter, digit by digit."""
    return "C V " + " ".join(str(tracking_number))


def call_language(complaint: dict) -> str:
    """The complaint's language if we have the lines for it, else English."""
    lang = complaint.get("language") or "kn-IN"
    return lang if lang in QUESTION else "en-IN"


def question_text(tracking_number: int, complaint: dict, lang: str) -> str:
    summary = (complaint.get("summary_local") if lang != "en-IN" else None) or complaint.get("summary_en") or ""
    return QUESTION[lang].format(complaint=spoken_id(tracking_number), summary=summary.strip().rstrip("."))


# ---- one call-back, from "please ring" to the citizen's answer ---------------------------------

@dataclass
class Session:
    """One ringing (or answered) call-back. `on_result(answer, heard_text)` is called exactly once:
    answer is yes / no / unclear / no_answer / failed."""
    tracking_number: int
    complaint: dict
    language: str
    classify: Callable[[str, str], str]
    on_result: Callable[[str, str], None]
    issued: float = field(default_factory=time.time)
    answered: bool = False
    call_uuid: str = ""  # Vobiz's id for the call, from the answer webhook (to hang up)
    done: bool = False

    def finish(self, answer: str, heard: str = "") -> None:
        with _lock:
            if self.done:
                return
            self.done = True
        try:
            self.on_result(answer, heard)
        except Exception:
            log.exception("call-back result for CV-%s not recorded", self.tracking_number)


_sessions: dict[str, Session] = {}
_lock = threading.Lock()


def _forget_old(now: float) -> None:
    for t, sess in list(_sessions.items()):
        if now - sess.issued > SESSION_TTL_S:
            _sessions.pop(t, None)


def session(token: str) -> Session | None:
    with _lock:
        s = _sessions.get(token)
    return s if s and time.time() - s.issued <= SESSION_TTL_S else None


def end_session(token: str) -> None:
    with _lock:
        _sessions.pop(token, None)


def place_call(to_number: str, sess: Session) -> str | None:
    """Ask Vobiz to ring the citizen. Returns the session token, or None if Vobiz refused.
    Vobiz fetches /api/phone/callback/answer/<token> when they pick up."""
    s = get_settings()
    base = s.public_base_url.rstrip("/")
    if not (s.vobiz_auth_id and s.vobiz_auth_token and s.vobiz_phone_number and base and to_number):
        log.warning("call-back not placed: phone line or public address not configured")
        return None
    token = secrets.token_urlsafe(24)
    with _lock:
        _forget_old(time.time())
        _sessions[token] = sess
    try:
        r = httpx.post(
            f"{vobiz.API.format(auth_id=s.vobiz_auth_id)}/Call/",
            headers={"X-Auth-ID": s.vobiz_auth_id, "X-Auth-Token": s.vobiz_auth_token},
            json={"from": s.vobiz_phone_number, "to": to_number,
                  "answer_url": f"{base}/api/phone/callback/answer/{token}", "answer_method": "POST",
                  "hangup_url": f"{base}/api/phone/callback/hangup/{token}", "hangup_method": "POST",
                  "ring_timeout": RING_TIMEOUT_S},
            timeout=10,
        )
    except httpx.HTTPError as e:
        log.warning("call-back for CV-%s failed: %s", sess.tracking_number, type(e).__name__)
        end_session(token)
        return None
    if r.status_code not in (200, 201, 202):
        log.warning("call-back for CV-%s: Vobiz HTTP %s", sess.tracking_number, r.status_code)
        end_session(token)
        return None
    return token


# ---- the call itself ------------------------------------------------------------------------

def _pcm(text: str, lang: str) -> tuple[bytes, int]:
    wav, _ = sarvam.speak(text, lang, sample_rate=audio.RATE)
    return audio.wav_to_pcm(wav)


class CallbackCall:
    """The audio side of one answered call-back (Vobiz's stream events in, our speech out)."""

    def __init__(self, ws, stream_id: str, call_uuid: str, sess: Session):
        self.ws = ws
        self.stream_id = stream_id
        self.call_uuid = call_uuid
        self.sess = sess
        self.lang = sess.language
        self.eos = audio.EndOfSpeech(silence_ms=ANSWER_SILENCE_MS)
        self.listening = False
        self.asks = 0
        self.asked_at = time.monotonic()
        self.started = time.monotonic()
        self.finished = False
        self._played: dict[str, asyncio.Event] = {}
        self._n = 0
        self.task: asyncio.Task | None = None  # hearing the answer (finished even if they hang up)

    async def _send(self, msg: dict) -> None:
        await self.ws.send_text(json.dumps(msg))

    async def play(self, pcm: bytes, rate: int) -> None:
        """Queue audio on the call and wait until Vobiz reports it has played (same protocol as call.py)."""
        for piece in audio.chunks(pcm, rate):
            await self._send({"event": "playAudio", "streamId": self.stream_id, "media": {
                "contentType": "audio/x-l16", "sampleRate": rate,
                "payload": base64.b64encode(piece).decode()}})
        self._n += 1
        name = f"cb-{self._n}"
        done = self._played.setdefault(name, asyncio.Event())
        await self._send({"event": "checkpoint", "streamId": self.stream_id, "name": name})
        try:
            await asyncio.wait_for(done.wait(), timeout=len(pcm) / (rate * 2) + 2.0)
        except asyncio.TimeoutError:
            self._played.pop(name, None)

    async def say(self, text: str) -> bool:
        try:
            pcm, rate = await asyncio.to_thread(_pcm, text, self.lang)
        except (sarvam.SpeechError, ValueError) as e:
            log.warning("call-back %s: tts failed: %s", self.call_uuid, e)
            return False
        try:
            await self.play(pcm, rate)
        except Exception as e:  # they hung up: the answer still counts
            log.info("call-back %s: could not play (%s)", self.call_uuid, type(e).__name__)
            return False
        return True

    async def start(self) -> None:
        if not await self.say(question_text(self.sess.tracking_number, self.sess.complaint, self.lang)):
            return await self.finish("failed")
        self.ask_done()

    def ask_done(self) -> None:
        self.asks += 1
        self.eos.reset()
        self.asked_at = time.monotonic()
        self.listening = True

    def on_audio(self, pcm: bytes) -> None:
        if not self.listening or self.finished:
            return
        utterance = self.eos.feed(pcm)
        if utterance is not None:
            self.listening = False
            self.task = asyncio.create_task(self.hear(utterance))

    def on_played(self, name: str) -> None:
        event = self._played.pop(name, None)
        if event:
            event.set()

    async def hear(self, pcm: bytes) -> None:
        try:
            heard = await asyncio.to_thread(sarvam.transcribe, audio.pcm_to_wav(pcm), "speech.wav", "audio/wav")
            text = heard.text
        except sarvam.SpeechError as e:
            log.warning("call-back %s: stt failed: %s", self.call_uuid, e)
            text = ""
        answer = await asyncio.to_thread(self.sess.classify, text, self.lang) if text else "unclear"
        if answer == "unclear" and self.asks < MAX_ASKS:
            await self.say(LINES["again"][self.lang])
            return self.ask_done()
        await self.say(LINES[answer][self.lang])
        await self.finish(answer, text)

    async def watchdog(self) -> None:
        """Silence after the question: ask once more, then give up."""
        while not self.finished:
            await asyncio.sleep(1)
            if time.monotonic() - self.started > MAX_CALL_S:
                return await self.finish("unclear")
            if not self.listening or self.eos.hearing_speech:
                continue
            if time.monotonic() - self.asked_at > WAIT_FOR_ANSWER_S:
                self.listening = False
                if self.asks < MAX_ASKS:
                    await self.say(LINES["again"][self.lang])
                    self.ask_done()
                else:
                    await self.say(LINES["unclear"][self.lang])
                    return await self.finish("no_answer")

    async def finish(self, answer: str, heard: str = "") -> None:
        if self.finished:
            return
        self.finished = True
        self.listening = False
        await asyncio.to_thread(self.sess.finish, answer, heard)
        await asyncio.to_thread(vobiz.hang_up, self.call_uuid)
