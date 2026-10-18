"""The Telegram bot, with fake Telegram, fake speech, fake Gemma and a fake database. No network."""

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import contact, main
from app.channels import chat, telegram
from app.clerk import clerk as clerk_mod
from app.db.repo import FiledComplaint
from app.llm.types import LLMReply, ToolCall
from app.settings import get_settings
from app.speech.sarvam import Heard

client = TestClient(main.app)
SECRET = "test-secret_123"
CHAT = 555
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


class FakeApi:
    """Stands in for Telegram: records what the bot sends, serves fake files."""
    sent: list = []

    def __init__(self, token): pass
    def download(self, file_id): return b"OggS" + bytes(2000) if file_id.startswith("voice") else b"\xff\xd8jpeg"
    def send_text(self, chat_id, text): FakeApi.sent.append(("text", chat_id, text))
    def send_voice(self, chat_id, audio, mime): FakeApi.sent.append(("voice", chat_id, mime))
    def typing(self, chat_id): pass


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "telegram_bot_token", "123:fake")
    monkeypatch.setattr(s, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(s, "contact_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(s, "feature_photo_check", True)
    monkeypatch.setattr(chat, "Repo", FakeRepo)
    monkeypatch.setattr(telegram, "TelegramApi", FakeApi)
    monkeypatch.setattr(chat.sarvam, "speak", lambda text, lang, codec=None: (MP3, 3))
    monkeypatch.setattr(clerk_mod.router, "generate", lambda **_: LLMReply("ಯಾವ area?", [], "fake", "fake", 5))
    FakeRepo.filed, FakeRepo.calls, FakeApi.sent = [], [], []
    telegram.clerk.clear()
    telegram._seen.clear()


_next_id = iter(range(1, 10_000))


def post(message: dict, update_id: int | None = None, secret: str | None = SECRET):
    update = {"update_id": update_id or next(_next_id),
              "message": {"chat": {"id": CHAT, "type": "private"}, **message}}
    headers = {"X-Telegram-Bot-Api-Secret-Token": secret} if secret is not None else {}
    return client.post("/webhooks/telegram", json=update, headers=headers)


def texts():
    return [t for kind, _, t in FakeApi.sent if kind == "text"]


def test_a_wrong_or_missing_secret_is_refused():
    assert post({"text": "hello"}, secret="wrong").status_code == 401
    assert post({"text": "hello"}, secret=None).status_code == 401
    assert FakeApi.sent == []


def test_no_bot_token_means_no_telegram(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_bot_token", "")
    assert post({"text": "hello"}).status_code == 404


def test_no_secret_configured_refuses_everything(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "")
    assert post({"text": "hello"}, secret="").status_code == 401


def test_a_typed_message_gets_the_clerks_reply_in_text_only():
    r = post({"text": "road alli tumba potholes"})
    assert r.status_code == 200
    assert texts() == ["ಯಾವ area?"]
    assert not [s for s in FakeApi.sent if s[0] == "voice"]
    assert FakeRepo.calls == ["telegram"]


def test_one_conversation_per_chat():
    post({"text": "road alli potholes"})
    post({"text": "Yelahanka"})
    assert FakeRepo.calls == ["telegram"]  # the second message continued the same conversation
    assert telegram.clerk._chats[str(CHAT)].conv.state.caller_turn == 2


def test_a_voice_note_is_heard_and_answered_in_text_and_voice(monkeypatch):
    heard = []
    monkeypatch.setattr(chat.sarvam, "transcribe",
                        lambda data, name, mime: heard.append((name, mime, data[:4])) or Heard("ರಸ್ತೆ ಹಾಳಾಗಿದೆ", "kn-IN", 4))
    post({"voice": {"file_id": "voice-1", "duration": 4, "mime_type": "audio/ogg"}})
    assert heard == [("voice.ogg", "audio/ogg", b"OggS")]  # Sarvam takes Telegram's OGG/Opus as it is
    assert texts() == ["ಯಾವ area?"]
    assert ("voice", str(CHAT), "audio/mpeg") in FakeApi.sent


def test_a_long_voice_note_is_refused_before_downloading(monkeypatch):
    monkeypatch.setattr(chat.sarvam, "transcribe", lambda *a: pytest.fail("should not transcribe"))
    post({"voice": {"file_id": "voice-1", "duration": 90}})
    assert texts() == [telegram.TOO_LONG]


def test_the_same_update_twice_is_handled_once():
    post({"text": "hello"}, update_id=99)
    post({"text": "hello"}, update_id=99)
    assert len(texts()) == 1


def test_group_chats_are_ignored():
    client.post("/webhooks/telegram", headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
                json={"update_id": 5, "message": {"chat": {"id": -1, "type": "group"}, "text": "hi"}})
    assert FakeApi.sent == []


def file_at(place_id: str):
    """Gemma files at once at the given place."""
    return LLMReply("", [ToolCall("t1", "file_complaint", {
        "category": "road", "summary_en": "Pothole", "place_id": place_id, "caller_confirmed": True})],
        "fake", "fake", 5)


def test_a_location_pin_is_the_place_and_the_chat_can_be_reached_later(monkeypatch):
    lat, lon = 13.0957, 77.5790  # Yelahanka New Town bus station
    monkeypatch.setattr(clerk_mod.router, "generate", lambda **_: file_at(f"pin:{lat:.5f},{lon:.5f}"))
    post({"location": {"latitude": lat, "longitude": lon}})
    [fields] = FakeRepo.filed
    assert (fields["lat"], fields["lon"]) == (lat, lon)
    assert fields["place_name"].startswith("Location pin near ")
    assert fields["channel"] == "telegram"
    assert contact.unseal(fields["contact_enc"]) == ("telegram", str(CHAT))
    assert "CV-1042" in texts()[0] and "C V," not in texts()[0]  # written for reading, not for the ear


def test_the_filing_message_is_written_for_a_chat_not_read_out_on_a_call(monkeypatch):
    lat, lon = 13.0957, 77.5790
    monkeypatch.setattr(clerk_mod.router, "generate", lambda **_: file_at(f"pin:{lat:.5f},{lon:.5f}"))
    post({"location": {"latitude": lat, "longitude": lon}})
    done = texts()[0]
    assert done.count("CV-1042") == 1  # said once: a reader can scroll back
    assert "Once more" not in done and "calling" not in done and "ಇನ್ನೊಂದ್ಸಲ" not in done


def test_a_pin_outside_bengaluru_is_not_a_place(monkeypatch):
    told = []
    monkeypatch.setattr(clerk_mod.router, "generate",
                        lambda **k: told.append(k["messages"][-1].text) or LLMReply("ok", [], "f", "f", 1))
    post({"location": {"latitude": 28.61, "longitude": 77.21}})  # Delhi
    assert "outside Bengaluru" in told[0]
    assert telegram.clerk._chats[str(CHAT)].conv.state.offered == {}


def test_a_photo_is_described_to_the_clerk_and_kept_with_the_complaint(monkeypatch):
    saved, told = [], []
    monkeypatch.setattr(chat.vision, "look_at_problem",
                        lambda photo, cats: {"is_civic_problem": True, "category": "road", "severity": 4,
                                             "what_i_see": "A deep pothole on a tarred road"})
    monkeypatch.setattr(chat.db, "add_photo", lambda *a: saved.append(a) or 1)
    monkeypatch.setattr(clerk_mod.router, "generate",
                        lambda **k: told.append(k["messages"][-1].text) or LLMReply("Where is it?", [], "f", "f", 1))
    post({"photo": [{"file_id": "small", "file_size": 100}, {"file_id": "big", "file_size": 9000}],
          "caption": "near my house"})
    assert "A deep pothole on a tarred road" in told[0] and "near my house" in told[0]
    assert saved == []  # nothing to attach it to yet

    lat, lon = 13.0957, 77.5790
    monkeypatch.setattr(clerk_mod.router, "generate", lambda **_: file_at(f"pin:{lat:.5f},{lon:.5f}"))
    post({"location": {"latitude": lat, "longitude": lon}})
    [(number, kind, mime, data, verdict)] = saved
    assert (number, kind, mime) == (1042, "citizen", "image/jpeg")
    assert verdict["what_i_see"] == "A deep pothole on a tarred road"


def test_an_image_sent_as_a_file_counts_as_a_photo(monkeypatch):
    # CV-1013, 18 Oct: "water.webp" sent as a file from Telegram Desktop was dropped; only the caption arrived.
    seen, told = [], []
    monkeypatch.setattr(chat.vision, "look_at_problem",
                        lambda photo, cats: seen.append(photo[0]) or {"is_civic_problem": True,
                                                                      "what_i_see": "Water leaking from a pipe"})
    monkeypatch.setattr(clerk_mod.router, "generate",
                        lambda **k: told.append(k["messages"][-1].text) or LLMReply("Where?", [], "f", "f", 1))
    post({"document": {"file_id": "d", "file_name": "water.webp", "mime_type": "image/webp", "file_size": 39000},
          "caption": "water leakage in doddaballapura"})
    assert seen == ["image/webp"]
    assert "Water leaking from a pipe" in told[0] and "doddaballapura" in told[0]


def test_a_file_that_is_not_an_image_is_not_treated_as_a_photo(monkeypatch):
    monkeypatch.setattr(chat.vision, "look_at_problem", lambda *a: pytest.fail("not an image"))
    post({"document": {"file_id": "d", "file_name": "bill.pdf", "mime_type": "application/pdf"}, "caption": "hello"})


def test_a_photo_right_after_filing_goes_to_that_complaint(monkeypatch):
    saved = []
    monkeypatch.setattr(chat.vision, "look_at_problem", lambda photo, cats: {"what_i_see": "pothole"})
    monkeypatch.setattr(chat.db, "add_photo", lambda *a: saved.append(a) or 1)
    lat, lon = 13.0957, 77.5790
    monkeypatch.setattr(clerk_mod.router, "generate", lambda **_: file_at(f"pin:{lat:.5f},{lon:.5f}"))
    post({"location": {"latitude": lat, "longitude": lon}})
    post({"photo": [{"file_id": "p", "file_size": 100}]})
    assert [s[:2] for s in saved] == [(1042, "citizen")]
    assert "CV-1042" in texts()[-1]


def test_start_gets_the_welcome_without_using_gemma(monkeypatch):
    monkeypatch.setattr(clerk_mod.router, "generate", lambda **_: pytest.fail("no Gemma for /start"))
    post({"text": "/start"})
    assert texts() == [chat.WELCOME]


def test_a_sticker_gets_how_to_and_starts_nothing():
    post({"sticker": {"file_id": "s"}})
    assert texts() == [chat.HOW_TO] and FakeRepo.calls == []


def test_one_chat_cannot_flood_gemma():
    for _ in range(chat.RATE_LIMIT_MESSAGES + 1):
        post({"text": "hello there"})
    assert texts()[-1] == chat.BUSY and texts().count(chat.BUSY) == 1


# ---- call-back after a fix: "is it really fixed?" ------------------------------------------------

COMPLAINT = {"tracking_id": "CV-1042", "language": "kn-IN", "summary_en": "Streetlight broken",
             "summary_local": "street light ಕೆಲಸ ಮಾಡ್ತಿಲ್ಲ", "status": "fixed"}


@pytest.fixture
def answers(monkeypatch):
    """Fake Gemma reading the answer, and a record of what reaches the timeline."""
    got = []
    monkeypatch.setattr(chat.followup, "classify", lambda text, lang: {"ಹೌದು": "yes", "ಇಲ್ಲ": "no"}.get(text, "unclear"))
    monkeypatch.setattr(chat.followup, "record_answer", lambda n, answer, heard="", attempt=1, channel="": got.append(
        (n, answer, heard, channel)))
    return got


def test_the_fixed_question_goes_out_through_the_registered_telegram_sender(answers):
    from app import followup

    assert followup._chat_senders["telegram"] is telegram.ask_fixed
    assert telegram.ask_fixed(str(CHAT), 1042, COMPLAINT) is True
    assert "CV-1042" in texts()[-1] and "ಹೌದು" in texts()[-1]  # in the complaint's language


def test_a_clear_answer_is_recorded_and_thanked_not_sent_to_the_clerk(answers):
    telegram.ask_fixed(str(CHAT), 1042, COMPLAINT)
    post({"text": "ಹೌದು"})
    assert answers == [(1042, "yes", "ಹೌದು", "telegram")]
    assert "CV-1042" in texts()[-1] and FakeRepo.calls == []  # no clerk conversation was started
    post({"text": "ಇಲ್ಲ"})  # asked once, answered once: a later message is just a message
    assert len(answers) == 1 and texts()[-1] == "ಯಾವ area?"


def test_an_unclear_answer_is_recorded_and_the_message_still_reaches_the_clerk(answers):
    telegram.ask_fixed(str(CHAT), 1042, COMPLAINT)
    post({"text": "there is garbage near the school"})
    assert answers == [(1042, "unclear", "there is garbage near the school", "telegram")]
    assert texts()[-1] == "ಯಾವ area?"


def test_no_question_without_a_bot_token(monkeypatch, answers):
    monkeypatch.setattr(get_settings(), "telegram_bot_token", "")
    assert telegram.ask_fixed(str(CHAT), 1042, COMPLAINT) is False and FakeApi.sent == []


def test_a_google_maps_link_is_used_as_the_exact_spot(monkeypatch):
    # 18 Oct: citizens paste a Google Maps link for a precise location.
    told = []
    monkeypatch.setattr(clerk_mod.router, "generate",
                        lambda **k: told.append(k["messages"][-1].text) or LLMReply("ok", [], "f", "f", 1))
    post({"text": "pothole here https://www.google.com/maps/place/X/@13.0433,77.5126,17z please fix"})
    assert "Google Maps link" in told[0] and "https://" not in told[0]
    assert "pin:13.04330,77.51260" in telegram.clerk._chats[str(CHAT)].conv.state.offered


def test_an_unreadable_maps_link_makes_the_clerk_ask_for_a_landmark(monkeypatch):
    told = []
    monkeypatch.setattr(chat.maps_link, "location", lambda url: None)
    monkeypatch.setattr(clerk_mod.router, "generate",
                        lambda **k: told.append(k["messages"][-1].text) or LLMReply("ok", [], "f", "f", 1))
    post({"text": "pothole https://maps.app.goo.gl/broken"})
    assert "could not be read" in told[0]
