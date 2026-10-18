"""The try-it page's server side, with fake speech, fake Gemma and a fake database."""

import pytest
from fastapi.testclient import TestClient

from app import main
from app.api import try_it
from app.clerk import clerk as clerk_mod
from app.llm.types import LLMReply
from app.speech.sarvam import Heard

client = TestClient(main.app)
TINY_WAV = __import__("app.phone.audio", fromlist=["pcm_to_wav"]).pcm_to_wav(bytes(320))  # 10 ms of silence


class FakeRepo:
    def start_call(self, *a, **k): return 7
    def add_turn(self, *a, **k): pass
    def add_events(self, *a, **k): pass
    def end_call(self, *a, **k): pass


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    monkeypatch.setattr(try_it, "Repo", FakeRepo)
    monkeypatch.setattr(try_it.sarvam, "speak", lambda text, lang: (TINY_WAV, 3))
    monkeypatch.setattr(try_it.sarvam, "transcribe", lambda *a: Heard("ರಸ್ತೆಯಲ್ಲಿ ಹಳ್ಳಗಳು ಇವೆ", "kn-IN", 4))
    monkeypatch.setattr(clerk_mod.router, "generate", lambda **_: LLMReply("ಯಾವ area?", [], "fake", "fake", 5))
    try_it._sessions.clear()
    try_it._turn_times.clear()
    try_it._spoken.clear()
    try_it._greeting_audio = None


def start():
    return client.post("/api/try/start").json()["session_id"]


def test_typed_turn_gets_a_spoken_reply():
    sid = start()
    r = client.post("/api/try/turn", data={"session_id": sid, "text": "road alli tumba potholes"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "ಯಾವ area?"
    assert body["language"] == "kn-IN"  # the reply is Kannada, so it is voiced in Kannada
    voice = client.post("/api/try/speak", data={"session_id": sid})
    assert voice.status_code == 200 and voice.headers["content-type"] == "audio/wav"


def test_speak_only_voices_the_clerks_own_reply():
    sid = start()
    assert client.post("/api/try/speak", data={"session_id": sid}).status_code == 404  # nothing said yet
    assert client.post("/api/try/speak", data={"session_id": "nope"}).status_code == 404


def test_spoken_turn_is_transcribed_first():
    sid = start()
    r = client.post("/api/try/turn", data={"session_id": sid},
                    files={"audio": ("a.webm", b"x" * 5000, "audio/webm")})
    assert r.status_code == 200
    assert r.json()["caller_text"] == "ರಸ್ತೆಯಲ್ಲಿ ಹಳ್ಳಗಳು ಇವೆ"
    assert r.json()["language"] == "kn-IN"


def test_oversized_recording_is_refused():
    sid = start()
    r = client.post("/api/try/turn", data={"session_id": sid},
                    files={"audio": ("a.webm", b"x" * (try_it.MAX_AUDIO_BYTES + 1), "audio/webm")})
    assert r.status_code == 413


def test_unknown_session_is_404():
    r = client.post("/api/try/turn", data={"session_id": "nope", "text": "hi"})
    assert r.status_code == 404


def test_one_visitor_cannot_flood_gemma():
    sid = start()
    codes = [client.post("/api/try/turn", data={"session_id": sid, "text": "hello there"}).status_code
             for _ in range(try_it.RATE_LIMIT_TURNS + 1)]
    assert codes[-1] == 429 and set(codes[:-1]) == {200}


def test_visitors_behind_railways_proxy_are_counted_separately():
    """On Railway every request arrives from the proxy; X-Real-IP (set by Railway's edge) tells visitors apart."""
    sid = start()
    for _ in range(try_it.RATE_LIMIT_TURNS):
        client.post("/api/try/turn", data={"session_id": sid, "text": "hello"}, headers={"X-Real-IP": "203.0.113.1"})
    one = client.post("/api/try/turn", data={"session_id": sid, "text": "hello"}, headers={"X-Real-IP": "203.0.113.1"})
    other = client.post("/api/try/turn", data={"session_id": sid, "text": "hello"}, headers={"X-Real-IP": "203.0.113.2"})
    assert (one.status_code, other.status_code) == (429, 200)


def test_greeting_is_spoken_once_and_reused(monkeypatch):
    calls = []
    monkeypatch.setattr(try_it.sarvam, "speak", lambda t, l: calls.append((t, l)) or (TINY_WAV, 1))
    start()
    start()
    assert [lang for _, lang in calls] == ["kn-IN", "hi-IN", "en-IN"]  # each part in its own language, once


def test_a_reply_can_be_voiced_at_most_twice():
    sid = start()
    client.post("/api/try/turn", data={"session_id": sid, "text": "road alli potholes"})
    codes = [client.post("/api/try/speak", data={"session_id": sid}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# ---- a browser citizen leaves a number for the call-back (18 Oct: browser citizens could not be reached) ----

class ContactRepo(FakeRepo):
    saved: list = []

    def set_contact(self, complaint_id, contact_enc, last4):
        ContactRepo.saved.append((complaint_id, contact_enc, last4))
        return True


def filed_session(monkeypatch):
    from cryptography.fernet import Fernet
    from app.db.repo import FiledComplaint
    from app.settings import get_settings
    monkeypatch.setattr(get_settings(), "contact_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(try_it, "Repo", ContactRepo)
    ContactRepo.saved = []
    sid = start()
    try_it._sessions[sid][0].state.filed = FiledComplaint(41, 1041)
    return sid


def test_a_browser_citizen_can_leave_a_number_for_the_call_back(monkeypatch):
    from app.contact import unseal
    sid = filed_session(monkeypatch)
    r = client.post("/api/try/contact", json={"session_id": sid, "phone": "98450 12345"})
    assert r.status_code == 200 and r.json()["last4"] == "2345"
    [(row, sealed, last4)] = ContactRepo.saved
    assert row == 41 and last4 == "2345" and unseal(sealed) == ("phone", "+919845012345")


@pytest.mark.parametrize("phone", ["12345", "98450 1234", "5845012345", "+1 415 555 0100", ""])
def test_only_an_indian_mobile_number_is_accepted(monkeypatch, phone):
    sid = filed_session(monkeypatch)
    assert client.post("/api/try/contact", json={"session_id": sid, "phone": phone}).status_code == 422
    assert ContactRepo.saved == []


def test_no_number_before_the_complaint_is_filed(monkeypatch):
    sid = filed_session(monkeypatch)
    try_it._sessions[sid][0].state.filed = None
    assert client.post("/api/try/contact", json={"session_id": sid, "phone": "9845012345"}).status_code == 409
