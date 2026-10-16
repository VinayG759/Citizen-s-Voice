"""One live phone call over Vobiz's audio stream.

Turn-taking (half-duplex): the caller speaks → we notice they stopped → Sarvam
transcribes → the Gemma clerk decides → Sarvam speaks the reply → we listen again.
If the reply takes longer than a second, a short "one moment" plays so the line
is never silent. While the clerk is speaking, the caller's audio is ignored.
"""

import asyncio
import base64
import json
import logging
import time

from app import events
from app.clerk.clerk import Conversation
from app.phone import audio, vobiz
from app.speech import sarvam

log = logging.getLogger(__name__)

FALLBACK_FILLER_AFTER_S = 3.0  # only if neither Gemma's own words nor its reply have arrived by then
NUDGE_AFTER_S = 10  # silence → "are you there?"
GIVE_UP_AFTER_S = 25  # silence → goodbye
MAX_CALL_S = 6 * 60
FIRST_TURN_SILENCE_MS = 1500  # people settle in on the first turn; don't cut them off
SILENCE_MS = 1200  # a real call cut a caller off mid-sentence at 0.7 s

# The greeting: each language spoken in its own voice settings, then joined. The caller answers in
# the language they want (see clerk/language.py).
GREETING = [
    ("ನಮಸ್ಕಾರ, Citizen's Voice ಗೆ ಸ್ವಾಗತ. ಕನ್ನಡದಲ್ಲಿ ಮಾತಾಡೋಕೆ, ಕನ್ನಡದಲ್ಲೇ ಹೇಳಿ.", "kn-IN"),
    ("हिंदी में बात करने के लिए, हिंदी में बोलिए.", "hi-IN"),
    ("For English, just speak in English. Please tell me the problem in your area.", "en-IN"),
]

# Fixed lines, written the way people SAY them (the voice reads spelling literally: "ಒಂದ್ನಿಮಿಷ",
# not "ಒಂದು ನಿಮಿಷ"). Lists rotate so the caller doesn't hear the same words every time.
LINES = {
    "filler": {
        "kn-IN": ["ಸರಿ, ಒಂದ್ನಿಮಿಷ.", "ಹಾಂ, ಒಂದ್ಸೆಕೆಂಡ್.", "ಓಕೆ, ನೋಡ್ತಿದ್ದೀನಿ."],
        "hi-IN": ["ठीक है, एक मिनट.", "हाँ, एक सेकंड.", "अच्छा, देख रही हूँ."],
        "en-IN": ["Okay, one moment.", "Sure, just a second.", "Alright, checking."],
        "ta-IN": ["சரி, ஒரு நிமிஷம்.", "ஒரு செகண்ட்."],
        "te-IN": ["సరే, ఒక్క నిమిషం.", "ఒక్క సెకండ్."],
    },
    "sorry": {
        "kn-IN": ["ಕ್ಷಮಿಸಿ, ಸರಿಯಾಗಿ ಕೇಳಿಸ್ಲಿಲ್ಲ. ಇನ್ನೊಂದ್ಸಲ ಹೇಳ್ತೀರಾ?"],
        "hi-IN": ["माफ़ कीजिए, ठीक से सुनाई नहीं दिया. एक बार फिर बताएँगे?"],
        "en-IN": ["Sorry, I didn't catch that. Could you say it once more?"],
        "ta-IN": ["மன்னிக்கவும், சரியா கேட்கல. இன்னொரு தடவை சொல்ல முடியுமா?"],
        "te-IN": ["క్షమించండి, సరిగ్గా వినపడలేదు. ఇంకోసారి చెప్తారా?"],
    },
    "nudge": {
        "kn-IN": ["ಹಲೋ, line ಅಲ್ಲಿ ಇದ್ದೀರಾ? ನಿಧಾನವಾಗಿ ಹೇಳಿ, ನಾನು ಕೇಳ್ತಿದ್ದೀನಿ."],
        "hi-IN": ["हलो, आप line पर हैं? आराम से बताइए, मैं सुन रही हूँ."],
        "en-IN": ["Hello, are you still there? Take your time, I'm listening."],
        "ta-IN": ["ஹலோ, line-ல இருக்கீங்களா? நிதானமா சொல்லுங்க, நான் கேட்டுக்கிட்டு இருக்கேன்."],
        "te-IN": ["హలో, line లో ఉన్నారా? నెమ్మదిగా చెప్పండి, నేను వింటున్నాను."],
    },
    "goodbye": {
        "kn-IN": ["ಸರಿ, ಏನಾದ್ರೂ ಬೇಕಾದ್ರೆ ಮತ್ತೆ call ಮಾಡಿ. ಧನ್ಯವಾದಗಳು."],
        "hi-IN": ["ठीक है, कुछ भी ज़रूरत हो तो फिर call कीजिए. धन्यवाद."],
        "en-IN": ["Alright, call us again any time. Thank you."],
        "ta-IN": ["சரி, ஏதாவது தேவைன்னா மறுபடியும் call பண்ணுங்க. நன்றி."],
        "te-IN": ["సరే, ఏదైనా అవసరమైతే మళ్ళీ call చేయండి. ధన్యవాదాలు."],
    },
    "technical": {
        "kn-IN": ["ಕ್ಷಮಿಸಿ, ನಮ್ಮ ಕಡೆ ಒಂದು technical problem ಆಯ್ತು. ಸ್ವಲ್ಪ ಹೊತ್ತಾದ ಮೇಲೆ ಮತ್ತೆ call ಮಾಡಿ."],
        "hi-IN": ["माफ़ कीजिए, हमारी तरफ़ एक technical problem आ गई. थोड़ी देर बाद फिर call कीजिए."],
        "en-IN": ["Sorry, we have a technical problem on our side. Please call again in a little while."],
        "ta-IN": ["மன்னிக்கவும், எங்க பக்கம் ஒரு technical problem. கொஞ்ச நேரம் கழிச்சு call பண்ணுங்க."],
        "te-IN": ["క్షమించండి, మా వైపు technical problem వచ్చింది. కాసేపటి తర్వాత మళ్ళీ call చేయండి."],
    },
}
_clip_cache: dict[tuple, tuple[bytes, int]] = {}
_rotation: dict[tuple, int] = {}


def _pcm(text: str, lang: str) -> tuple[bytes, int]:
    key = ("text", text, lang)
    if key not in _clip_cache:
        wav, _ = sarvam.speak(text, lang, sample_rate=audio.RATE)
        _clip_cache[key] = audio.wav_to_pcm(wav)
    return _clip_cache[key]


def greeting_pcm() -> tuple[bytes, int]:
    parts = [_pcm(text, lang) for text, lang in GREETING]
    return b"".join(p for p, _ in parts), audio.RATE


def greeting_text() -> str:
    return " ".join(text for text, _ in GREETING)


def clip(name: str, lang: str = "kn-IN") -> tuple[bytes, int]:
    """A fixed line in the call's language (English if we have no version), rotating variants."""
    options = LINES[name].get(lang) or LINES[name]["en-IN"]
    i = _rotation.get((name, lang), 0)
    _rotation[(name, lang)] = i + 1
    return _pcm(options[i % len(options)], lang if lang in LINES[name] else "en-IN")


def warm_clips() -> None:
    try:
        greeting_pcm()
    except Exception as e:  # warming is best-effort; lines are made on first use otherwise
        log.warning("could not prepare greeting: %s", e)
    for name, by_lang in LINES.items():
        for lang, texts in by_lang.items():
            for text in texts:
                try:
                    _pcm(text, lang)
                except Exception as e:
                    log.warning("could not prepare %s/%s: %s", name, lang, e)


class PhoneCall:
    def __init__(self, ws, stream_id: str, call_uuid: str, conv: Conversation):
        self.ws = ws
        self.stream_id = stream_id
        self.call_uuid = call_uuid
        self.conv = conv
        self.eos = audio.EndOfSpeech(silence_ms=FIRST_TURN_SILENCE_MS)
        self.listening = False
        self.last_heard = time.monotonic()
        self.started = time.monotonic()
        self.nudged = False
        self.finished = False
        self._played: dict[str, asyncio.Event] = {}
        self._n = 0
        self.task: asyncio.Task | None = None

    # ---- sending audio -------------------------------------------------
    async def _send(self, msg: dict) -> None:
        await self.ws.send_text(json.dumps(msg))

    async def play(self, pcm: bytes, rate: int, wait: bool = True) -> None:
        """Queue audio on the call; optionally wait until Vobiz reports it has played."""
        for piece in audio.chunks(pcm, rate):
            await self._send({"event": "playAudio", "streamId": self.stream_id, "media": {
                "contentType": "audio/x-l16", "sampleRate": rate,
                "payload": base64.b64encode(piece).decode()}})
        self._n += 1
        name = f"say-{self._n}"
        done = self._played.setdefault(name, asyncio.Event())
        await self._send({"event": "checkpoint", "streamId": self.stream_id, "name": name})
        if wait:
            seconds = len(pcm) / (rate * 2)
            try:  # if the caller hangs up, the "played" event never comes
                await asyncio.wait_for(done.wait(), timeout=seconds + 2.0)
            except asyncio.TimeoutError:
                self._played.pop(name, None)

    async def say_clip(self, name: str, wait: bool = True) -> None:
        """A fixed line, in the language this call is in."""
        pcm, rate = await asyncio.to_thread(clip, name, self.conv.language)
        await self.play(pcm, rate, wait)

    async def say_text(self, text: str, lang: str) -> None:
        """Speak words Gemma just produced (not a fixed line), without waiting for playback."""
        try:
            wav, _ = await asyncio.to_thread(sarvam.speak, text, lang, audio.RATE)
            await self.play(*audio.wav_to_pcm(wav), wait=False)
        except (sarvam.SpeechError, ValueError) as e:
            log.warning("call %s: interim tts failed: %s", self.call_uuid, e)

    # ---- the conversation --------------------------------------------
    async def start(self) -> None:
        pcm, rate = await asyncio.to_thread(greeting_pcm)
        await self.play(pcm, rate)
        self.listen()

    def listen(self) -> None:
        self.eos.reset()
        self.listening = True
        self.last_heard = time.monotonic()

    def on_audio(self, pcm: bytes) -> None:
        if not self.listening or self.finished:
            return
        if self.eos.hearing_speech:
            self.last_heard = time.monotonic()
        utterance = self.eos.feed(pcm)
        if utterance is not None:
            self.listening = False
            self.task = asyncio.create_task(self.respond(utterance))

    def on_played(self, name: str) -> None:
        event = self._played.pop(name, None)
        if event:
            event.set()

    async def respond(self, pcm: bytes) -> None:
        t0 = time.monotonic()
        try:
            heard = await asyncio.to_thread(sarvam.transcribe, audio.pcm_to_wav(pcm), "speech.wav", "audio/wav")
        except sarvam.SpeechError as e:
            log.warning("call %s: stt failed: %s", self.call_uuid, e)
            await self.say_clip("sorry")
            return self.listen()
        if not heard.text:
            await self.say_clip("sorry")
            return self.listen()

        # When Gemma uses a tool it also says a few words ("ಸರಿ, Jayanagar, ನೋಡ್ತೀನಿ…"); those are
        # spoken straight away while the tool runs. They come from a worker thread, so hand them to
        # this event loop.
        loop = asyncio.get_running_loop()
        interim: list[asyncio.Future] = []
        self.conv.on_interim = lambda text, lang: interim.append(
            asyncio.run_coroutine_threadsafe(self.say_text(text, lang), loop))
        turn = asyncio.create_task(asyncio.to_thread(self.conv.turn, heard.text, heard.language))
        done, _ = await asyncio.wait({turn}, timeout=FALLBACK_FILLER_AFTER_S)
        if not done and not interim:
            await self.say_clip("filler", wait=False)  # last resort: nothing from Gemma yet
        result = await turn
        for f in interim:  # Gemma's own interim words go out before its reply
            await asyncio.wrap_future(f)
        self.eos.silence_ms = SILENCE_MS  # after the first turn, the normal patience

        try:
            wav, tts_ms = await asyncio.to_thread(sarvam.speak, result.reply, result.language, audio.RATE)
            pcm_out, rate = audio.wav_to_pcm(wav)
        except (sarvam.SpeechError, ValueError) as e:
            log.warning("call %s: tts failed: %s", self.call_uuid, e)
            pcm_out, rate, tts_ms = None, audio.RATE, 0
        first_audio_ms = int((time.monotonic() - t0) * 1000)
        log.info("call %s turn: stt %dms, gemma %dms, tts %dms, caller waited %dms",
                 self.call_uuid, heard.ms, result.llm_ms, tts_ms, first_audio_ms)

        if pcm_out:
            await self.play(pcm_out, rate)
        else:
            await self.say_clip("technical")
        asyncio.create_task(asyncio.to_thread(self._save, heard, result, tts_ms))

        if result.complaint or result.ended:
            await self.finish("filed" if result.complaint else "abandoned")
        else:
            self.listen()

    def _save(self, heard, result, tts_ms: int) -> None:
        try:
            repo, cid = self.conv.repo, self.conv.call_id
            repo.add_turn(cid, "caller", heard.text, heard.language, stt_ms=heard.ms)
            repo.add_turn(cid, "clerk", result.reply, result.language, llm_ms=result.llm_ms, tts_ms=tts_ms or None)
            repo.add_events(cid, result.events)
        except Exception:
            log.exception("could not save phone turn")

    async def watchdog(self) -> None:
        """Nudges a silent caller, ends abandoned or overlong calls."""
        while not self.finished:
            await asyncio.sleep(1)
            if time.monotonic() - self.started > MAX_CALL_S:
                await self.say_clip("goodbye")
                return await self.finish("abandoned")
            if not self.listening or self.eos.hearing_speech:
                continue
            quiet = time.monotonic() - self.last_heard
            if quiet > GIVE_UP_AFTER_S:
                await self.say_clip("goodbye")
                return await self.finish("abandoned")
            if quiet > NUDGE_AFTER_S and not self.nudged:
                self.nudged = True
                self.listening = False
                await self.say_clip("nudge")
                self.listen()

    async def finish(self, outcome: str) -> None:
        if self.finished:
            return
        self.finished = True
        self.listening = False
        filed = self.conv.state.filed
        await asyncio.to_thread(self._end, outcome, filed.id if filed else None)
        await asyncio.to_thread(vobiz.hang_up, self.call_uuid)

    def _end(self, outcome: str, complaint_id: int | None) -> None:
        events.publish("call_ended", call_id=self.conv.call_id, channel="phone", outcome=outcome)
        try:
            self.conv.repo.end_call(self.conv.call_id, outcome, complaint_id)
        except Exception:
            log.exception("could not close call record")
