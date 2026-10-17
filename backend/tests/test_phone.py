"""The phone line, end to end with a simulated Vobiz, caller audio, Gemma and Sarvam."""

import base64
import json
import math
from array import array

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import main
from app.api import phone as phone_api
from app.clerk import clerk as clerk_mod
from app.llm.types import LLMReply
from app.phone import audio, call as call_mod
from app.speech.sarvam import Heard

client = TestClient(main.app)
RATE = 16000


def tone(ms: int, amplitude: int = 6000) -> bytes:
    n = RATE * ms // 1000
    return array("h", (int(amplitude * math.sin(2 * math.pi * 300 * i / RATE)) for i in range(n))).tobytes()


def silence(ms: int) -> bytes:
    return bytes(RATE * 2 * ms // 1000)


# ---- noticing when the caller stops talking ----------------------------------

def feed_all(eos, pcm):
    out = None
    for i in range(0, len(pcm), 640):  # 20 ms chunks, as Vobiz sends them
        out = eos.feed(pcm[i:i + 640]) or out
    return out


def test_an_utterance_ends_after_a_pause():
    eos = audio.EndOfSpeech(silence_ms=700)
    assert feed_all(eos, silence(500) + tone(1200)) is None  # still talking
    utterance = feed_all(eos, silence(800))
    assert utterance is not None
    assert 1.8 <= len(utterance) / (RATE * 2) <= 2.1  # the speech plus the pause, not the leading silence


def test_a_short_click_is_not_speech():
    eos = audio.EndOfSpeech()
    assert feed_all(eos, tone(60) + silence(1000)) is None


def test_background_hum_is_not_speech():
    eos = audio.EndOfSpeech()
    assert feed_all(eos, tone(3000, amplitude=150)) is None


def test_a_monologue_is_cut_at_the_limit():
    eos = audio.EndOfSpeech(max_ms=3000)
    assert feed_all(eos, tone(3500)) is not None


def test_wav_round_trip():
    pcm = tone(100)
    assert audio.wav_to_pcm(audio.pcm_to_wav(pcm)) == (pcm, RATE)


# ---- Vobiz webhooks ------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean():
    phone_api._tokens.clear()
    phone_api._calls_by_caller.clear()
    call_mod._clip_cache.clear()


def answer(caller="+919876543210", uuid="call-1"):
    return client.post("/api/phone/answer", data={"CallUUID": uuid, "From": caller, "To": "+918065356055"})


def test_answer_streams_audio_with_a_one_time_token(monkeypatch):
    # Without a configured public address the stream address comes from the request's Host header;
    # a PUBLIC_BASE_URL in the developer's .env must not change what this test sees.
    monkeypatch.setattr(phone_api.get_settings(), "public_base_url", "")
    r = answer()
    assert r.headers["content-type"].startswith("application/xml")
    assert 'bidirectional="true"' in r.text and "audio/x-l16;rate=16000" in r.text
    assert "wss://testserver/api/phone/stream/" in r.text


def test_a_stream_without_a_valid_token_is_refused():
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/phone/stream/made-up-token") as ws:
            ws.receive_text()


def test_one_number_cannot_call_endlessly():
    for i in range(phone_api.CALLS_PER_HOUR_PER_CALLER):
        assert "<Stream" in answer(uuid=f"c{i}").text
    assert "<Hangup" in answer(uuid="one-too-many").text


def test_caller_identity_keeps_only_a_hash_and_last_four():
    h, last4 = phone_api.caller_identity("+91 98765 43210")
    assert last4 == "3210" and "9876543210" not in h and len(h) == 64


# ---- a whole call --------------------------------------------------------------

class FakeRepo:
    def __init__(self):
        self.turns, self.ended = [], []

    def start_call(self, *a, **k): return 42
    def add_turn(self, *a, **k): self.turns.append(a)
    def add_events(self, *a, **k): pass
    def end_call(self, *a, **k): self.ended.append(a)


def test_a_call_greets_listens_and_answers(monkeypatch):
    repo = FakeRepo()
    monkeypatch.setattr(phone_api, "Repo", lambda: repo)
    spoken = []

    def fake_speak(text, lang, sample_rate=None):
        spoken.append(text)
        return audio.pcm_to_wav(tone(200)), 5

    monkeypatch.setattr(call_mod.sarvam, "speak", fake_speak)
    monkeypatch.setattr(call_mod.sarvam, "transcribe", lambda *a: Heard("ರಸ್ತೆಯಲ್ಲಿ ಹಳ್ಳಗಳು", "kn-IN", 10))
    monkeypatch.setattr(clerk_mod.router, "generate", lambda **_: LLMReply("ಯಾವ area?", [], "fake", "fake", 5))
    monkeypatch.setattr(call_mod.vobiz, "hang_up", lambda uuid: True)

    token = answer().text.split("/api/phone/stream/")[1].split("<")[0]
    with client.websocket_connect(f"/api/phone/stream/{token}") as ws:
        ws.send_text(json.dumps({"event": "start", "start": {
            "callId": "call-1", "streamId": "s-1", "mediaFormat": {"encoding": "audio/x-l16", "sampleRate": 16000}}}))

        def next_event(kind):
            while True:
                m = json.loads(ws.receive_text())
                if m["event"] == kind:
                    return m

        greeting = next_event("playAudio")
        assert greeting["media"]["contentType"] == "audio/x-l16" and greeting["streamId"] == "s-1"
        ws.send_text(json.dumps({"event": "playedStream", "name": next_event("checkpoint")["name"]}))

        # the caller speaks, then pauses longer than the first-turn patience (1.5 s)
        for chunk in audio.chunks(tone(1000) + silence(call_mod.FIRST_TURN_SILENCE_MS + 200), RATE, ms=20):
            ws.send_text(json.dumps({"event": "media", "media": {
                "payload": base64.b64encode(chunk).decode()}}))
        next_event("playAudio")  # the clerk's reply starts playing
        ws.send_text(json.dumps({"event": "playedStream", "name": next_event("checkpoint")["name"]}))
        ws.send_text(json.dumps({"event": "stop"}))

    assert spoken[0].startswith("ನಮಸ್ಕಾರ")  # greeting
    assert "ಯಾವ area?" in spoken  # Gemma's reply was spoken


def test_a_short_pause_mid_sentence_does_not_end_the_turn():
    # Real call, 16 Oct: a caller pausing to think was cut off at 0.7 s.
    eos = audio.EndOfSpeech(silence_ms=call_mod.SILENCE_MS)
    assert feed_all(eos, tone(800) + silence(900) + tone(800)) is None  # still talking after a 0.9 s pause


def test_fixed_lines_follow_the_call_language_and_rotate(monkeypatch):
    said = []
    monkeypatch.setattr(call_mod.sarvam, "speak", lambda t, l, sample_rate=None: said.append((t, l)) or (audio.pcm_to_wav(tone(50)), 1))
    call_mod.clip("filler", "en-IN")
    call_mod.clip("filler", "en-IN")
    call_mod.clip("sorry", "hi-IN")
    assert said[0][1] == "en-IN" and said[0][0] != said[1][0]  # English, and not the same words twice
    assert said[2] == (call_mod.LINES["sorry"]["hi-IN"][0], "hi-IN")
