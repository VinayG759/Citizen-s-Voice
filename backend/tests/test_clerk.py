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
    clerk_tools.find_place(conv.state, "Presidency University")
    conv.state.caller_turn = 2
    args = dict(category="road", summary_en="Potholes", place_id=PRESIDENCY, caller_confirmed=True)
    first = clerk_tools.file_complaint(conv.state, repo, {}, **args)
    second = clerk_tools.file_complaint(conv.state, repo, {}, **args)
    assert first["tracking_id"] == second["tracking_id"] == "CV-1001"
    assert len(repo.filed) == 1


def test_unknown_category_is_refused():
    state = clerk_tools.ToolState()
    clerk_tools.find_place(state, "Presidency University")
    state.caller_turn = 2
    out = clerk_tools.file_complaint(state, FakeRepo(), {}, category="aliens", summary_en="x",
                                     place_id=PRESIDENCY, caller_confirmed=True)
    assert out["not_filed"]


def test_emergency_makes_the_complaint_urgent():
    repo = FakeRepo()
    state = clerk_tools.ToolState()
    clerk_tools.raise_emergency(state, "open manhole")
    clerk_tools.find_place(state, "Presidency University")
    state.caller_turn = 2
    clerk_tools.file_complaint(state, repo, {}, category="drainage", summary_en="Open manhole",
                               place_id=PRESIDENCY, caller_confirmed=True, urgency=2)
    assert repo.filed[0]["urgency"] == 5 and repo.filed[0]["is_emergency"] is True


def test_status_lookup_accepts_spoken_forms():
    repo = FakeRepo()
    assert clerk_tools.get_complaint_status(repo, "C V 1 0 4 2")["status"] == "in_progress"
    assert clerk_tools.get_complaint_status(repo, "CV-9999")["found"] is False


def test_tracking_id_is_spoken_one_character_at_a_time():
    assert clerk_tools.spoken_id(1042) == "C V 1 0 4 2"


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
    clerk_tools.find_place(conv.state, "Presidency University")
    conv.state.caller_turn = 1
    scripted(monkeypatch, [
        call("file_complaint", category="road", summary_en="Potholes", place_id=PRESIDENCY, caller_confirmed=True),
        # no further reply scripted: a second model call would raise StopIteration
    ])
    result = conv.turn("ಹೌದು")
    assert "C V 1 0 0 1" in result.reply and result.complaint == {"tracking_id": "CV-1001"}


def test_a_wrong_script_reply_is_retried_with_the_bigger_model_and_a_reminder(monkeypatch):
    from app.llm import router
    calls = []

    def fake_openrouter(**kw):
        calls.append((kw["model"], "IMPORTANT" in kw["system"]))
        text = "ಯಾವ area ಅಲ್ಲಿ ఉన్నాయి?" if len(calls) == 1 else "ಯಾವ area ಅಲ್ಲಿ ಇದೆ?"
        return LLMReply(text, [], "openrouter", kw["model"], 5)

    monkeypatch.setattr(router.get_settings(), "gemini_api_key", "")
    monkeypatch.setattr(router.openrouter, "generate", fake_openrouter)
    reply = router.generate(system="clerk", messages=[], tools=[], caller_language="kn-IN")
    assert reply.text == "ಯಾವ area ಅಲ್ಲಿ ಇದೆ?"
    assert calls == [("google/gemma-4-26b-a4b-it", False), ("google/gemma-4-31b-it", True)]
