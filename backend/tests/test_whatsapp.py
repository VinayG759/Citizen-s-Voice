"""The WhatsApp channel, with a fake Graph API (at the HTTP level), fake speech, fake Gemma and a
fake database. No network."""

import hashlib
import hmac
import json

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import contact, main
from app.channels import chat, whatsapp
from app.clerk import clerk as clerk_mod
from app.db.repo import FiledComplaint
from app.llm.types import LLMReply, ToolCall
from app.settings import get_settings
from app.speech.sarvam import Heard

client = TestClient(main.app)
APP_SECRET = "app-secret"
TOKEN = "EAA-fake-token"
PHONE_ID = "1065"
WA_ID = "919800000001"
MP3 = b"ID3" + bytes(100)


class FakeRepo:
    filed: list = []
    calls: list = []

    def start_call(self, channel, caller_hash=None, **_):
        FakeRepo.calls.append(channel)
        return 7

    def add_turn(self, *a, **k): pass
    def add_events(self, *a, **k): pass
    def end_call(self, *a, **k): pass
    def nearby_open(self, *a, **k): return []

    def file_complaint(self, **fields):
        FakeRepo.filed.append(fields)
        return FiledComplaint(1, 1042)


class FakeGraph:
    """Meta's Graph API: media lookups, media downloads, uploads and sends."""
    sent: list = []  # bodies posted to /messages
    media = {"voice-1": ("audio/ogg; codecs=opus", b"OggS" + bytes(2000)), "img-1": ("image/jpeg", b"\xff\xd8jpeg")}
    sizes: dict = {}

    def __call__(self, method, url, headers=None, timeout=None, **kw):
        assert headers == {"Authorization": f"Bearer {TOKEN}"}  # every call carries the token, in the header
        path = url.removeprefix(whatsapp.GRAPH + "/")
        if method == "GET" and path in self.media:
            mime, data = self.media[path]
            return httpx.Response(200, json={"url": f"https://lookaside.example/{path}", "mime_type": mime,
                                             "file_size": self.sizes.get(path, len(data))})
        if method == "GET" and url.startswith("https://lookaside.example/"):
            return httpx.Response(200, content=self.media[url.rsplit("/", 1)[1]][1])
        if method == "POST" and path == f"{PHONE_ID}/media":
            assert kw["data"]["type"] == "audio/mpeg"
            return httpx.Response(200, json={"id": "uploaded-1"})
        if method == "POST" and path == f"{PHONE_ID}/messages":
            FakeGraph.sent.append(kw["json"])
            return httpx.Response(200, json={"messages": [{"id": "wamid.out"}]})
        return httpx.Response(404, json={"error": {"message": "unknown"}})


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "whatsapp_access_token", TOKEN)
    monkeypatch.setattr(s, "whatsapp_phone_number_id", PHONE_ID)
    monkeypatch.setattr(s, "whatsapp_app_secret", APP_SECRET)
    monkeypatch.setattr(s, "whatsapp_verify_token", "verify-me")
    monkeypatch.setattr(s, "contact_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(s, "feature_photo_check", True)
    monkeypatch.setattr(chat, "Repo", FakeRepo)
    monkeypatch.setattr(whatsapp.httpx, "request", FakeGraph())
    monkeypatch.setattr(chat.sarvam, "speak", lambda text, lang, codec=None: (MP3, 3))
    monkeypatch.setattr(clerk_mod.router, "generate", lambda **_: LLMReply("ಯಾವ area?", [], "fake", "fake", 5))
    FakeRepo.filed, FakeRepo.calls, FakeGraph.sent, FakeGraph.sizes = [], [], [], {}
    whatsapp.clerk.clear()
    whatsapp._seen.clear()


_next_id = iter(range(1, 10_000))


def post(message: dict, msg_id: str | None = None, secret: str = APP_SECRET, to: str = PHONE_ID):
    body = json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": to}, "contacts": [{"wa_id": WA_ID}],
        "messages": [{"from": WA_ID, "id": msg_id or f"wamid.{next(_next_id)}", "timestamp": "1", **message}],
    }}]}]}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/whatsapp", content=body,
                       headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})


def texts():
    return [b["text"]["body"] for b in FakeGraph.sent if b["type"] == "text"]


def test_the_handshake_echoes_the_challenge_only_for_our_verify_token():
    ok = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                                  "hub.challenge": "1158201444"})
    assert ok.status_code == 200 and ok.text == "1158201444"
    bad = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "guess",
                                                   "hub.challenge": "1"})
    assert bad.status_code == 403
    assert client.get("/webhooks/whatsapp").status_code == 403


def test_no_verify_token_configured_refuses_the_handshake(monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_verify_token", "")
    r = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"})
    assert r.status_code == 403


def test_a_bad_or_missing_signature_is_refused():
    assert post({"type": "text", "text": {"body": "hi"}}, secret="wrong").status_code == 401
    r = client.post("/webhooks/whatsapp", json={"entry": []})
    assert r.status_code == 401
    assert FakeGraph.sent == []


def test_no_app_secret_configured_refuses_everything(monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", "")
    assert post({"type": "text", "text": {"body": "hi"}}, secret="").status_code == 401


def test_no_access_token_means_no_whatsapp(monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_access_token", "")
    assert post({"type": "text", "text": {"body": "hi"}}).status_code == 404
    assert client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe"}).status_code == 404


def test_a_text_message_gets_the_clerks_reply():
    assert post({"type": "text", "text": {"body": "road alli tumba potholes"}}).status_code == 200
    assert texts() == ["ಯಾವ area?"]
    assert FakeGraph.sent[0]["to"] == WA_ID and FakeGraph.sent[0]["messaging_product"] == "whatsapp"
    assert FakeRepo.calls == ["whatsapp"]


def test_messages_for_another_number_are_ignored():
    post({"type": "text", "text": {"body": "hi"}}, to="someone-else")
    assert FakeGraph.sent == []


def test_a_voice_note_is_heard_and_answered_in_text_and_audio(monkeypatch):
    heard = []
    monkeypatch.setattr(chat.sarvam, "transcribe",
                        lambda data, name, mime: heard.append((mime, data[:4])) or Heard("ರಸ್ತೆ ಹಾಳಾಗಿದೆ", "kn-IN", 4))
    post({"type": "audio", "audio": {"id": "voice-1", "mime_type": "audio/ogg; codecs=opus", "voice": True}})
    assert heard == [("audio/ogg", b"OggS")]  # downloaded with the token; Sarvam takes OGG/Opus as it is
    assert texts() == ["ಯಾವ area?"]
    assert {"type": "audio", "audio": {"id": "uploaded-1"}}.items() <= FakeGraph.sent[-1].items()


def test_a_long_voice_note_is_refused_before_downloading(monkeypatch):
    FakeGraph.sizes["voice-1"] = whatsapp.MAX_VOICE_BYTES + 1
    monkeypatch.setattr(chat.sarvam, "transcribe", lambda *a: pytest.fail("should not transcribe"))
    post({"type": "audio", "audio": {"id": "voice-1"}})
    assert texts() == [chat.TOO_LONG]


def test_an_image_is_described_and_kept_with_the_complaint(monkeypatch):
    saved, told = [], []
    monkeypatch.setattr(chat.vision, "look_at_problem",
                        lambda photo, cats: {"is_civic_problem": True, "category": "road", "severity": 4,
                                             "what_i_see": "A deep pothole"})
    monkeypatch.setattr(chat.db, "add_photo", lambda *a: saved.append(a) or 1)
    monkeypatch.setattr(clerk_mod.router, "generate",
                        lambda **k: told.append(k["messages"][-1].text) or LLMReply("Where?", [], "f", "f", 1))
    post({"type": "image", "image": {"id": "img-1", "caption": "near my house", "mime_type": "image/jpeg"}})
    assert "A deep pothole" in told[0] and "near my house" in told[0]

    lat, lon = 13.0957, 77.5790
    monkeypatch.setattr(clerk_mod.router, "generate", lambda **_: LLMReply("", [ToolCall("t1", "file_complaint", {
        "category": "road", "summary_en": "Pothole", "place_id": f"pin:{lat:.5f},{lon:.5f}",
        "caller_confirmed": True})], "f", "f", 1))
    post({"type": "location", "location": {"latitude": lat, "longitude": lon}})
    [(number, kind, mime, data, _)] = saved
    assert (number, kind, mime, data) == (1042, "citizen", "image/jpeg", b"\xff\xd8jpeg")
    [fields] = FakeRepo.filed
    assert (fields["lat"], fields["lon"], fields["channel"]) == (lat, lon, "whatsapp")
    assert contact.unseal(fields["contact_enc"]) == ("whatsapp", WA_ID)
    assert "CV-1042" in texts()[-1]


def test_the_same_message_twice_is_handled_once():
    post({"type": "text", "text": {"body": "hello"}}, msg_id="wamid.same")
    post({"type": "text", "text": {"body": "hello"}}, msg_id="wamid.same")
    assert len(texts()) == 1


def test_delivery_receipts_are_ignored():
    body = json.dumps({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": PHONE_ID},
                                                         "statuses": [{"id": "wamid.out", "status": "read"}]}}]}]}).encode()
    sig = "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert client.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sig}).status_code == 200
    assert FakeGraph.sent == [] and FakeRepo.calls == []


# ---- call-back after a fix: only inside Meta's 24-hour window ------------------------------------

COMPLAINT = {"tracking_id": "CV-1042", "language": "en-IN", "summary_en": "Streetlight broken", "status": "fixed"}


def test_the_fixed_question_is_sent_only_if_the_citizen_wrote_within_24_hours(monkeypatch):
    from app import followup

    notes = []
    monkeypatch.setattr(chat.db, "add_note", lambda n, note: notes.append((n, note)))
    assert followup._chat_senders["whatsapp"] is whatsapp.ask_fixed

    assert whatsapp.ask_fixed(WA_ID, 1042, COMPLAINT) is False  # never wrote to us (or before a restart)
    assert FakeGraph.sent == [] and notes and "24 h" in notes[0][1]

    post({"type": "text", "text": {"body": "hello"}})
    assert whatsapp.ask_fixed(WA_ID, 1042, COMPLAINT) is True
    assert "Is it really fixed?" in texts()[-1]

    whatsapp.clerk._seen_at[WA_ID] -= 25 * 3600  # the window has closed
    assert whatsapp.ask_fixed(WA_ID, 1042, COMPLAINT) is False and len(notes) == 2


def test_a_whatsapp_answer_reaches_the_timeline(monkeypatch):
    got = []
    monkeypatch.setattr(chat.followup, "classify", lambda text, lang: "no")
    monkeypatch.setattr(chat.followup, "record_answer", lambda n, a, heard="", attempt=1, channel="": got.append((n, a, channel)))
    post({"type": "text", "text": {"body": "hi"}})
    whatsapp.ask_fixed(WA_ID, 1042, COMPLAINT)
    post({"type": "text", "text": {"body": "still dark"}})
    assert got == [(1042, "no", "whatsapp")] and "reopened" in texts()[-1]
