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

FILLER_AFTER_S = 1.0  # play "one moment" if the reply isn't ready by then
NUDGE_AFTER_S = 10  # silence → "are you there?"
GIVE_UP_AFTER_S = 25  # silence → goodbye
MAX_CALL_S = 6 * 60

# Short fixed lines, spoken by Sarvam once and cached. Kannada first: the helpline's main language.
CLIPS = {
    "greeting": ("ನಮಸ್ಕಾರ, Citizen's Voice. ನಿಮ್ಮ area ಅಲ್ಲಿ ಏನು problem ಇದೆ ಹೇಳಿ. "
                 "You can also speak in English or Hindi.", "kn-IN"),
    "filler": ("ಹ್ಞೂ, ಒಂದು ನಿಮಿಷ.", "kn-IN"),
    "sorry": ("ಕ್ಷಮಿಸಿ, ಸರಿಯಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ.", "kn-IN"),
    "nudge": ("ಹಲೋ, ಇದ್ದೀರಾ? ನಿಮ್ಮ problem ಹೇಳಿ.", "kn-IN"),
    "goodbye": ("ಸರಿ, ಮತ್ತೆ call ಮಾಡಿ. ಧನ್ಯವಾದಗಳು.", "kn-IN"),
    "technical": ("ಕ್ಷಮಿಸಿ, ಒಂದು technical problem ಆಯ್ತು. ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಹೊತ್ತಿನ ನಂತರ call ಮಾಡಿ.", "kn-IN"),
}
_clip_cache: dict[str, tuple[bytes, int]] = {}


def clip(name: str) -> tuple[bytes, int]:
    """PCM and sample rate for a fixed line (spoken by Sarvam on first use, then cached)."""
    if name not in _clip_cache:
        text, lang = CLIPS[name]
        wav, _ = sarvam.speak(text, lang, sample_rate=audio.RATE)
        _clip_cache[name] = audio.wav_to_pcm(wav)
    return _clip_cache[name]


def warm_clips() -> None:
    for name in CLIPS:
        try:
            clip(name)
        except Exception as e:  # warming is best-effort; clips are made on first use otherwise
            log.warning("could not prepare clip %s: %s", name, e)


class PhoneCall:
    def __init__(self, ws, stream_id: str, call_uuid: str, conv: Conversation):
        self.ws = ws
        self.stream_id = stream_id
        self.call_uuid = call_uuid
        self.conv = conv
        self.eos = audio.EndOfSpeech()
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
        pcm, rate = await asyncio.to_thread(clip, name)
        await self.play(pcm, rate, wait)

    # ---- the conversation --------------------------------------------
    async def start(self) -> None:
        await self.say_clip("greeting")
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

        turn = asyncio.create_task(asyncio.to_thread(self.conv.turn, heard.text, heard.language))
        done, _ = await asyncio.wait({turn}, timeout=FILLER_AFTER_S)
        if not done:
            await self.say_clip("filler", wait=False)  # fills the silence while Gemma decides
        result = await turn

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
