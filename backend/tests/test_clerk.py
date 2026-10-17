"""The clerk's safety rules, tested with a scripted fake Gemma and a fake database."""

from datetime import datetime

import pytest

from app.clerk import clerk as clerk_mod
from app.clerk.clerk import Conversation
from app.db.repo import ComplaintStatus, FiledComplaint
from app.llm.router import foreign_script
from app.llm.types import LLMError, LLMReply, ToolCall
from app.tools import clerk_tools


class FakeRepo:
    def __init__(self):
        self.filed = []

    def file_complaint(self, **fields):
        self.filed.append(fields)
        return FiledComplaint(len(self.filed), 1000 + len(self.filed))

    def complaint_status(self, n):
        if n == 1042:
            return ComplaintStatus("CV-1042", "in_progress", "road", "Potholes", "Presidency University",
                                   datetime(2026, 10, 16))
        return None


def scripted(monkeypatch, replies):
    """Make Gemma return these replies in order."""
    it = iter(replies)

    def fake_generate(**_):
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(clerk_mod.router, "generate", fake_generate)


def say(text):
    return LLMReply(text, [], "fake", "fake", 5)


def call(name, **args):
    return LLMReply("", [ToolCall(f"id-{name}", name, args)], "fake", "fake", 5)


PRESIDENCY = "osm-w780259661"


def offer_presidency(state, turn=0):
    """Put the Rajanukunte campus in front of the tools directly: there are two Presidency University
    campuses in Bengaluru, and these tests are about filing rules, not search ranking."""
    from app.places import gazetteer as g
    state.offered[PRESIDENCY] = clerk_tools.OfferedPlace(g.by_id()[PRESIDENCY], turn)


def test_cannot_file_in_the_same_turn_the_place_was_found(monkeypatch):
    repo = FakeRepo()
    conv = Conversation(call_id=1, repo=repo)
    scripted(monkeypatch, [
        call("find_place", query="Presidency University", area="Rajanukunte"),
        call("file_complaint", category="road", summary_en="Potholes", place_id=PRESIDENCY, caller_confirmed=True),
        say("Presidency University, Rajanukunte ಅಲ್ವಾ?"),
    ])
    result = conv.turn("Presidency University gate hatra tumba potholes ide")
    assert repo.filed == []  # refused: the caller never got to confirm the place
    refused = [e for e in result.events if e["kind"] == "tool_result" and e["tool"] == "file_complaint"]
    assert refused[0]["result"]["not_filed"] is True


def test_files_after_caller_confirms_with_coordinates_from_data(monkeypatch):
    repo = FakeRepo()
    conv = Conversation(call_id=1, repo=repo)
    scripted(monkeypatch, [
        call("find_place", query="Presidency University", area="Rajanukunte"),
        say("Presidency University gate hatra road alli potholes. Sari na?"),
        call("file_complaint", category="road", summary_en="Many potholes on the road near Presidency University",
             place_id=PRESIDENCY, caller_confirmed=True, lat=0.0, lon=0.0),  # invented coordinates are ignored
        say("Complaint filed. Tracking ID C V 1 0 0 1."),
    ])
    conv.turn("Presidency University hatra potholes")
    result = conv.turn("haudu, sari")
    assert len(repo.filed) == 1
    filed = repo.filed[0]
    assert (round(filed["lat"], 3), round(filed["lon"], 3)) == (13.169, 77.535)  # from OpenStreetMap
    assert filed["place_name"] == "Presidency University"
    assert result.complaint == {"tracking_id": "CV-1001"}


def test_a_place_gemma_made_up_is_refused(monkeypatch):
    repo = FakeRepo()
    conv = Conversation(call_id=1, repo=repo)
    conv.state.caller_turn = 3
    out = clerk_tools.file_complaint(conv.state, repo, {}, category="road", summary_en="x",
                                     place_id="osm-n-invented", caller_confirmed=True)
    assert out["not_filed"] and repo.filed == []


def test_filing_twice_returns_the_first_complaint(monkeypatch):
    repo = FakeRepo()
    conv = Conversation(call_id=1, repo=repo)
    offer_presidency(conv.state)
    conv.state.caller_turn = 2
    args = dict(category="road", summary_en="Potholes", place_id=PRESIDENCY, caller_confirmed=True)
    first = clerk_tools.file_complaint(conv.state, repo, {}, **args)
    second = clerk_tools.file_complaint(conv.state, repo, {}, **args)
    assert first["tracking_id"] == second["tracking_id"] == "CV-1001"
    assert len(repo.filed) == 1


def test_unknown_category_is_refused():
    state = clerk_tools.ToolState()
    offer_presidency(state)
    state.caller_turn = 2
    out = clerk_tools.file_complaint(state, FakeRepo(), {}, category="aliens", summary_en="x",
                                     place_id=PRESIDENCY, caller_confirmed=True)
    assert out["not_filed"]


def test_emergency_makes_the_complaint_urgent():
    repo = FakeRepo()
    state = clerk_tools.ToolState()
    clerk_tools.raise_emergency(state, "open manhole")
    offer_presidency(state)
    state.caller_turn = 2
    clerk_tools.file_complaint(state, repo, {}, category="drainage", summary_en="Open manhole",
                               place_id=PRESIDENCY, caller_confirmed=True, urgency=2)
    assert repo.filed[0]["urgency"] == 5 and repo.filed[0]["is_emergency"] is True


def test_status_lookup_accepts_spoken_forms():
    repo = FakeRepo()
    assert clerk_tools.get_complaint_status(repo, "C V 1 0 4 2")["status"] == "the officer is working on it"
    assert clerk_tools.get_complaint_status(repo, "CV-9999")["found"] is False


def test_tracking_id_is_spoken_in_pairs():
    assert clerk_tools.spoken_id(1042) == "C V, 1 0, 4 2"  # digits in pairs, with pauses


def test_when_gemma_is_unreachable_the_caller_is_asked_to_repeat(monkeypatch):
    conv = Conversation(call_id=1, repo=FakeRepo(), language="kn-IN")
    scripted(monkeypatch, [LLMError("all providers failed")])
    result = conv.turn("hello")
    assert "ಕ್ಷಮಿಸಿ" in result.reply
    assert conv.messages == [] and conv.state.caller_turn == 0  # the failed turn left no trace


@pytest.mark.parametrize("text,lang,expected", [
    ("ಯಾವ area ಅಲ್ಲಿ ಈ பிரச்சினை?", "kn-IN", "ta"),  # Tamil word in a Kannada reply (seen in testing)
    ("ಯಾವ area ಅಲ್ಲಿ ఉన్నాయి?", "kn-IN", "te"),  # Telugu word (seen in testing)
    ("ಈ ಗುಂಡಿಗಳು ಯಾವಾಗ부터 ಇವೆ?", "kn-IN", "HANGUL"),  # Korean word on a real call, 16 Oct
    ("这是什么", "kn-IN", "CJK"),
    ("ಯಾವ area? Okay. ₹500, 5 ವರ್ಷ – ಸರಿ!", "kn-IN", None),
    ("நீங்கள் எங்கே?", "ta-IN", None),  # a Tamil caller may hear Tamil
    ("कौन सा area?", "hi-IN", None),
])
def test_wrong_script_is_detected(text, lang, expected):
    assert foreign_script(text, lang) == expected


def test_after_filing_the_tracking_id_is_read_out_without_another_model_call(monkeypatch):
    repo = FakeRepo()
    conv = Conversation(call_id=1, repo=repo, language="kn-IN")
    offer_presidency(conv.state)
    conv.state.caller_turn = 1
    scripted(monkeypatch, [
        call("file_complaint", category="road", summary_en="Potholes", place_id=PRESIDENCY, caller_confirmed=True),
        # no further reply scripted: a second model call would raise StopIteration
    ])
    result = conv.turn("ಹೌದು")
    assert "C V, 1 0, 0 1" in result.reply and result.complaint == {"tracking_id": "CV-1001"}


def test_a_wrong_script_reply_is_retried_with_the_bigger_model_and_a_reminder(monkeypatch):
    from app.llm import router
    calls = []

    def fake_openrouter(**kw):
        calls.append((kw["model"], "IMPORTANT" in kw["system"]))
        text = "ಯಾವ area ಅಲ್ಲಿ ఉన్నాయి?" if len(calls) == 1 else "ಯಾವ area ಅಲ್ಲಿ ಇದೆ?"
        return LLMReply(text, [], "openrouter", kw["model"], 5)

    monkeypatch.setattr(router.get_settings(), "gemini_api_key", "")
    monkeypatch.setattr(router.get_settings(), "openrouter_api_key", "test")  # never depend on the real .env
    monkeypatch.setattr(router.openrouter, "generate", fake_openrouter)
    reply = router.generate(system="clerk", messages=[], tools=[], caller_language="kn-IN")
    assert reply.text == "ಯಾವ area ಅಲ್ಲಿ ಇದೆ?"
    assert calls == [("google/gemma-4-26b-a4b-it", False), ("google/gemma-4-31b-it", True)]


def test_the_first_reply_chooses_the_language_and_it_stays():
    from app.clerk.language import LanguageLock
    lock = LanguageLock()
    assert lock.update("en-IN", "There are potholes near my house") == "en-IN"
    assert lock.update("kn-IN", "Presidency University gate") == "en-IN"   # one turn elsewhere: no flip
    assert lock.update("en-IN", "Yes, that's right") == "en-IN"
    assert lock.update("hi-IN", "हाँ") == "en-IN"
    assert lock.update("hi-IN", "मुझे हिंदी में बात करनी है, सड़क खराब है") == "hi-IN"  # two turns in a row: follow


def test_naming_a_language_chooses_it():
    from app.clerk.language import LanguageLock
    lock = LanguageLock()
    assert lock.update("kn-IN", "English") == "en-IN"
    assert lock.update("en-IN", "ಕನ್ನಡದಲ್ಲಿ ಮಾತಾಡಿ") == "kn-IN"


def test_urdu_callers_are_answered_in_hindi():
    from app.clerk.language import LanguageLock
    assert LanguageLock().update("ur-IN", "پانی نہیں آ رہا") == "hi-IN"


def test_one_turn_in_another_language_asks_before_switching():
    from app.clerk.language import LanguageLock
    lock = LanguageLock()
    lock.update("kn-IN", "ನಮ್ಮ road ಅಲ್ಲಿ ಹಳ್ಳಗಳು ಇವೆ")
    lock.update("en-IN", "Actually the potholes are near the bus stop")  # just speaks English
    assert lock.language == "kn-IN" and lock.pending == "en-IN"  # not switched yet: Gemma asks
    lock.update("en-IN", "Yes please")
    assert lock.language == "en-IN" and lock.pending is None


def test_a_place_name_inside_kannada_is_not_english():
    from app.clerk.language import LanguageLock
    lock = LanguageLock()
    lock.update("kn-IN", "Malleshwaram-ನಲ್ಲಿ ಕಸದ ತೊಟ್ಟಿಯನ್ನು clean ಮಾಡಿಲ್ಲ")
    # A real Telegram voice note, 17 Oct: Sarvam labelled it English and wrote ಎದುರು in Telugu letters.
    assert lock.update("en-IN", "Kadu Malleshwara Temple ఎదురు") == "kn-IN"
    assert lock.pending is None  # not even a question about switching
    lock.update("en-IN", "Actually it is near the bus stop")  # really English: still noticed
    assert lock.pending == "en-IN"


@pytest.mark.parametrize("text,expected", [
    ("ಸರಿ, gate ಹತ್ತಿರ… ಎಷ್ಟು ದಿನದಿಂದ?", "kn-IN"),
    ("अच्छा, 3-4 दिन… कहाँ पर?", "hi-IN"),
    ("Okay, two weeks. Which street?", "en-IN"),
    ("", "kn-IN"),
])
def test_each_reply_is_voiced_in_the_language_it_is_written_in(text, expected):
    from app.clerk.language import written_in
    assert written_in(text, "kn-IN") == expected
