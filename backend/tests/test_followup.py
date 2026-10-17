"""The call-back after a fix, with a simulated Vobiz, Sarvam, Gemma and database. No real calls."""

import base64
import json
import math
import time
from array import array

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import events, followup, main
from app.contact import seal
from app.llm.types import LLMError, LLMReply
from app.phone import audio, outbound
from app.settings import get_settings
from app.speech.sarvam import Heard

client = TestClient(main.app)
RATE = 16000
NUMBER = "+919876543210"


def tone(ms: int) -> bytes:
    n = RATE * ms // 1000
    return array("h", (int(6000 * math.sin(2 * math.pi * 300 * i / RATE)) for i in range(n))).tobytes()


def silence(ms: int) -> bytes:
    return bytes(RATE * 2 * ms // 1000)


class FakeRepo:
    def __init__(self, contact="phone", status="fixed", language="kn-IN", sensitive=False):
        self.complaint = {"tracking_id": "CV-1004", "status": status, "language": language,
                          "summary_en": "Potholes on 11th Main", "summary_local": "11ನೇ ಮೇನ್ ಅಲ್ಲಿ ಹಳ್ಳಗಳು",
                          "sensitive": sensitive, "urgency": 3}
        self.sealed = seal(contact, NUMBER if contact == "phone" else "chat-77") if contact else None
        self.changes, self.notes = [], []

    def contact_for(self, n):
        return (self.sealed, dict(self.complaint)) if n == 1004 else (None, None)

    def change_status(self, n, status, by, note=None):
        self.complaint["status"] = status
        if status == "reopened":
            self.complaint["urgency"] += 1
        self.changes.append((status, by, note))
        return dict(self.complaint)

    def add_note(self, n, note):
        self.notes.append(note)
        return True


@pytest.fixture
def setup(monkeypatch):
    s = get_settings()
    for k, v in {"feature_callback": True, "contact_encryption_key": Fernet.generate_key().decode(),
                 "vobiz_auth_id": "MA_TEST", "vobiz_auth_token": "tok", "vobiz_phone_number": "+918065356055",
                 "public_base_url": "https://cv.example"}.items():
        monkeypatch.setattr(s, k, v)
    published, retries, hung_up = [], [], []
    monkeypatch.setattr(events, "publish", lambda kind, **d: published.append({"type": kind, **d}))
    monkeypatch.setattr(followup, "within_calling_hours", lambda now=None: True)
    monkeypatch.setattr(followup, "_schedule_retry", lambda n, attempt: retries.append((n, attempt)))
    monkeypatch.setattr(outbound.vobiz, "hang_up", lambda uuid: hung_up.append(uuid) or True)
    monkeypatch.setattr(outbound.sarvam, "speak", lambda text, lang, sample_rate=None: (audio.pcm_to_wav(tone(100)), 5))
    followup._in_flight.clear()
    outbound._sessions.clear()

    def use(repo):
        monkeypatch.setattr(followup, "repo", repo)
        return repo

    return {"use": use, "published": published, "retries": retries, "hung_up": hung_up, "mp": monkeypatch}


def vobiz_accepts(monkeypatch, posted):
    def post(url, **kw):
        posted.append({"url": url, **kw})
        return httpx.Response(201, json={"request_uuid": "req-1", "message": "call fired"})
    monkeypatch.setattr(outbound.httpx, "post", post)


def states(published):
    return [e["state"] for e in published if e["type"] == "callback"]


FINISHED = {"confirmed", "reopened", "unclear", "no_answer", "failed", "skipped"}


def wait_until(done, seconds=10.0):
    """The answer is recorded from a worker thread: wait for it, generously, since a busy machine is slow."""
    deadline = time.monotonic() + seconds
    while not done() and time.monotonic() < deadline:
        time.sleep(0.02)


def talk(token: str, says: str | None) -> None:
    """Vobiz answers, streams the call; the citizen hears the question and says `says` (None: silence)."""
    xml = client.post(f"/api/phone/callback/answer/{token}", data={"CallUUID": "cb-1"}).text
    assert f"wss://cv.example/api/phone/callback/stream/{token}" in xml
    with client.websocket_connect(f"/api/phone/callback/stream/{token}") as ws:
        ws.send_text(json.dumps({"event": "start", "start": {"streamId": "s-1"}}))

        def played():
            while True:
                m = json.loads(ws.receive_text())
                if m["event"] == "checkpoint":
                    ws.send_text(json.dumps({"event": "playedStream", "name": m["name"]}))
                    return

        played()  # the question
        if says is not None:
            for chunk in audio.chunks(tone(800) + silence(outbound.ANSWER_SILENCE_MS + 200), RATE, ms=20):
                ws.send_text(json.dumps({"event": "media", "media": {"payload": base64.b64encode(chunk).decode()}}))
            played()  # the closing line
        ws.send_text(json.dumps({"event": "stop"}))


def ring_and_answer(setup, repo, says, gemma_says):
    mp = setup["mp"]
    posted = []
    vobiz_accepts(mp, posted)
    mp.setattr(outbound.sarvam, "transcribe", lambda *a: Heard(says, "kn-IN", 10))
    mp.setattr(followup.router, "generate", lambda **_: LLMReply(gemma_says, [], "fake", "fake", 5))
    setup["use"](repo)
    followup.ask_citizen(1004)
    assert len(posted) == 1
    token = posted[0]["json"]["answer_url"].rsplit("/", 1)[1]
    talk(token, says)
    wait_until(lambda: (repo.changes or repo.notes) and set(states(setup["published"])) & FINISHED)
    return posted[0]


# ---- the whole call ------------------------------------------------------------------------------

def test_yes_records_that_the_citizen_confirmed(setup):
    repo = FakeRepo()
    sent = ring_and_answer(setup, repo, "ಹೌದು, ಸರಿ ಆಗಿದೆ", '{"answer": "yes"}')
    assert repo.changes == [("fixed", "citizen", 'citizen confirmed it is fixed (phone call-back): "ಹೌದು, ಸರಿ ಆಗಿದೆ"')]
    assert states(setup["published"]) == ["calling", "answered", "confirmed"]
    assert setup["hung_up"] == ["cb-1"] and not setup["retries"]
    # we rang the number that filed, from our line, and Vobiz comes back to our addresses
    assert sent["json"]["to"] == NUMBER and sent["json"]["from"] == "+918065356055"
    assert sent["url"].endswith("/Account/MA_TEST/Call/") and sent["headers"]["X-Auth-ID"] == "MA_TEST"
    assert NUMBER not in json.dumps(setup["published"])  # the dashboard never sees the number


def test_no_reopens_the_complaint(setup):
    repo = FakeRepo()
    ring_and_answer(setup, repo, "ಇಲ್ಲ, ಇನ್ನೂ ಹಳ್ಳ ಇದೆ", '{"answer": "no"}')
    assert repo.changes[0][:2] == ("reopened", "citizen") and "NOT fixed" in repo.changes[0][2]
    assert repo.complaint["urgency"] == 4  # reopening raises its priority
    assert states(setup["published"])[-1] == "reopened"
    assert any(e["type"] == "complaint_updated" and e["status"] == "reopened" for e in setup["published"])


def test_unclear_twice_is_noted_and_tried_once_more_later(setup):
    repo = FakeRepo()
    mp = setup["mp"]
    mp.setattr(outbound, "MAX_ASKS", 1)  # don't re-ask inside the call, to keep the test short
    ring_and_answer(setup, repo, "ಯಾರು ಮಾತಾಡ್ತಿರೋದು?", '{"answer": "unclear"}')
    assert not repo.changes  # the status is never changed on a guess
    assert "couldn't tell" in repo.notes[0] and "try once more" in repo.notes[0]
    assert setup["retries"] == [(1004, 2)]


def test_the_question_names_the_complaint_digit_by_digit_in_its_language():
    c = {"language": "kn-IN", "summary_en": "Potholes", "summary_local": "ಹಳ್ಳಗಳು"}
    text = outbound.question_text(1004, c, outbound.call_language(c))
    assert "C V 1 0 0 4" in text and "ಹಳ್ಳಗಳು" in text and "ನಿಜವಾಗ್ಲೂ" in text
    ta = {"language": "ta-IN", "summary_en": "Potholes", "summary_local": "குழிகள்"}
    assert outbound.call_language(ta) == "en-IN"  # no Tamil lines yet: English, with the English summary
    assert "Potholes" in outbound.question_text(1004, ta, "en-IN")


# ---- results without a full call ---------------------------------------------------------------

def test_no_answer_is_noted_and_retried_once(setup):
    repo = setup["use"](FakeRepo())
    posted = []
    vobiz_accepts(setup["mp"], posted)
    followup.ask_citizen(1004)
    token = posted[0]["json"]["hangup_url"].rsplit("/", 1)[1]
    client.post(f"/api/phone/callback/hangup/{token}", data={"HangupCause": "NO_ANSWER"})
    assert "didn't answer" in repo.notes[0] and setup["retries"] == [(1004, 2)]
    assert states(setup["published"]) == ["calling", "no_answer"]


def test_second_attempt_does_not_retry_again(setup):
    repo = setup["use"](FakeRepo())
    followup.record_answer(1004, "no_answer", attempt=2)
    assert "try once more" not in repo.notes[0] and not setup["retries"]


def test_no_contact_means_no_call(setup):
    repo = setup["use"](FakeRepo(contact=None))
    followup.ask_citizen(1004)
    assert "no way to reach" in repo.notes[0] and states(setup["published"]) == ["skipped"]


def test_sensitive_reports_are_never_called(setup):
    repo = setup["use"](FakeRepo(sensitive=True))
    followup.ask_citizen(1004)
    assert not repo.changes and states(setup["published"]) == ["skipped"]


def test_feature_off_does_nothing(setup):
    setup["mp"].setattr(get_settings(), "feature_callback", False)
    repo = setup["use"](FakeRepo())
    followup.ask_citizen(1004)
    assert not repo.notes and not setup["published"]


def test_outside_calling_hours_no_call(setup):
    setup["mp"].setattr(followup, "within_calling_hours", lambda now=None: False)
    repo = setup["use"](FakeRepo())
    followup.ask_citizen(1004)
    assert "outside calling hours" in repo.notes[0]


def test_calling_hours_are_bengaluru_time():
    from datetime import datetime
    assert followup.within_calling_hours(datetime(2026, 10, 17, 4, 0, tzinfo=followup.timezone.utc))  # 9:30 AM IST
    assert not followup.within_calling_hours(datetime(2026, 10, 17, 15, 0, tzinfo=followup.timezone.utc))  # 8:30 PM


def test_reopened_meanwhile_means_no_call(setup):
    repo = setup["use"](FakeRepo(status="reopened"))
    followup.ask_citizen(1004)
    assert not repo.notes and not setup["published"]


def test_a_yes_after_an_officer_reopened_keeps_the_officers_status(setup):
    repo = setup["use"](FakeRepo(status="reopened"))
    followup.record_answer(1004, "yes", "ಹೌದು")
    assert not repo.changes and "already reopened" in repo.notes[0]


@pytest.mark.parametrize("vobiz", ["http_error", "refused"])
def test_vobiz_error_is_noted_and_retried(setup, vobiz):
    repo = setup["use"](FakeRepo())

    def post(url, **kw):
        if vobiz == "http_error":
            raise httpx.ConnectError("down")
        return httpx.Response(403, json={"error": "not allowed"})

    setup["mp"].setattr(outbound.httpx, "post", post)
    followup.ask_citizen(1004)
    assert "could not be made" in repo.notes[0] and setup["retries"] == [(1004, 2)]
    assert states(setup["published"]) == ["calling", "failed"] and not outbound._sessions


def test_one_call_back_at_a_time(setup):
    setup["use"](FakeRepo())
    posted = []
    vobiz_accepts(setup["mp"], posted)
    followup.ask_citizen(1004)
    followup.ask_citizen(1004)  # officer double-clicked "fixed"
    assert len(posted) == 1


def test_a_stream_needs_an_answered_call_back(setup):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/phone/callback/stream/made-up") as ws:
            ws.receive_text()
    assert "<Hangup" in client.post("/api/phone/callback/answer/made-up", data={"CallUUID": "x"}).text


# ---- reading the answer ----------------------------------------------------------------------

def test_classify_never_guesses(monkeypatch):
    monkeypatch.setattr(followup.router, "generate", lambda **_: LLMReply("I think so?", [], "f", "f", 1))
    assert followup.classify("ಹೌದು", "kn-IN") == "unclear"  # no JSON → unclear
    monkeypatch.setattr(followup.router, "generate", lambda **_: LLMReply('{"answer": "maybe"}', [], "f", "f", 1))
    assert followup.classify("ಹೌದು", "kn-IN") == "unclear"

    def down(**_):
        raise LLMError("down")
    monkeypatch.setattr(followup.router, "generate", down)
    assert followup.classify("ಹೌದು", "kn-IN") == "unclear"
    assert followup.classify("   ", "kn-IN") == "unclear"


# ---- chat channels (Telegram plugs in here) ----------------------------------------------------

def test_a_chat_contact_goes_to_its_channel(setup):
    repo = setup["use"](FakeRepo(contact="telegram"))
    sent = []
    setup["mp"].setattr(followup, "_chat_senders", {"telegram": lambda addr, n, c: sent.append((addr, n)) or True})
    followup.ask_citizen(1004)
    assert sent == [("chat-77", 1004)] and not repo.notes
    followup.record_answer(1004, "no", "still broken", channel="telegram")  # their reply, later
    assert repo.changes[0][0] == "reopened" and "telegram call-back" in repo.changes[0][2]


def test_a_chat_channel_not_built_yet_is_noted(setup):
    repo = setup["use"](FakeRepo(contact="telegram"))
    setup["mp"].setattr(followup, "_chat_senders", {})
    followup.ask_citizen(1004)
    assert "could not be made" in repo.notes[0]


def test_an_unclear_first_answer_gets_asked_once_more_in_the_same_call(setup):
    repo = setup["use"](FakeRepo())
    mp = setup["mp"]
    posted, said = [], []
    vobiz_accepts(mp, posted)
    heard = iter(["ಏನು?", "ಹೌದು, ಆಗಿದೆ"])
    mp.setattr(outbound.sarvam, "transcribe", lambda *a: Heard(next(heard), "kn-IN", 10))
    answers = iter(['{"answer": "unclear"}', '{"answer": "yes"}'])
    mp.setattr(followup.router, "generate", lambda **_: LLMReply(next(answers), [], "fake", "fake", 5))
    mp.setattr(outbound.sarvam, "speak", lambda text, lang, sample_rate=None: said.append(text) or (audio.pcm_to_wav(tone(100)), 5))
    followup.ask_citizen(1004)
    token = posted[0]["json"]["answer_url"].rsplit("/", 1)[1]
    client.post(f"/api/phone/callback/answer/{token}", data={"CallUUID": "cb-1"})
    with client.websocket_connect(f"/api/phone/callback/stream/{token}") as ws:
        ws.send_text(json.dumps({"event": "start", "start": {"streamId": "s-1"}}))

        def played():
            while True:
                m = json.loads(ws.receive_text())
                if m["event"] == "checkpoint":
                    return ws.send_text(json.dumps({"event": "playedStream", "name": m["name"]}))

        def speak():
            for chunk in audio.chunks(tone(800) + silence(outbound.ANSWER_SILENCE_MS + 200), RATE, ms=20):
                ws.send_text(json.dumps({"event": "media", "media": {"payload": base64.b64encode(chunk).decode()}}))

        played()   # the question
        speak()    # "ಏನು?"
        played()   # "sorry, is it fixed? say yes or no"
        speak()    # "ಹೌದು, ಆಗಿದೆ"
        played()   # thank you
        ws.send_text(json.dumps({"event": "stop"}))
    wait_until(lambda: repo.changes)
    assert said[1] == outbound.LINES["again"]["kn-IN"] and said[2] == outbound.LINES["yes"]["kn-IN"]
    assert repo.changes[0][:2] == ("fixed", "citizen")
