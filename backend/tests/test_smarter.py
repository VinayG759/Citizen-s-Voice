"""Phase 5: duplicate reports and 'what happened to my complaint?' — with a fake database."""

from datetime import datetime

import pytest

from app.clerk import clerk as clerk_mod
from app.clerk.clerk import Conversation
from app.db.repo import ComplaintStatus, FiledComplaint
from app.llm.types import LLMReply, Msg, ToolCall
from app.tools import clerk_tools

PRESIDENCY = "osm-w780259661"


def offer_presidency(state, turn=0):
    """Put the Rajanukunte campus in front of the tools directly: there are two Presidency University
    campuses in Bengaluru, and these tests are about filing rules, not search ranking."""
    from app.places import gazetteer as g
    state.offered[PRESIDENCY] = clerk_tools.OfferedPlace(g.by_id()[PRESIDENCY], turn)


class Repo:
    """One open pothole complaint (CV-1042, 3 reports so far) near Presidency University."""

    def __init__(self):
        self.added, self.filed = [], []

    def nearby_open(self, lat, lon, category, radius_m=150):
        if category != "road":
            return []
        return [{"tracking_id": "CV-1042", "tracking_number": 1042, "summary": "Potholes near the gate",
                 "place": "Presidency University", "report_count": 3, "metres_away": 40, "filed_on": "2026-10-15"}]

    def add_report(self, parent, **fields):
        self.added.append((parent, fields))
        return FiledComplaint(42, parent), 4, False

    def file_complaint(self, **fields):
        self.filed.append(fields)
        return FiledComplaint(1, 1001)

    def latest_for_caller(self, caller_hash):
        if caller_hash == "mine":
            return ComplaintStatus("CV-1004", "in_progress", "road", "Potholes", "St. Mary's School",
                                   datetime(2026, 10, 16))
        return None

    def complaint_status(self, n):
        return None


def ready_state():
    s = clerk_tools.ToolState()
    offer_presidency(s)
    s.caller_turn = 2
    return s


def test_nearby_finds_the_existing_complaint_without_exposing_internal_ids():
    s, repo = ready_state(), Repo()
    out = clerk_tools.find_nearby_complaints(s, repo, PRESIDENCY, "road")
    assert out["matches"][0]["tracking_id"] == "CV-1042" and "tracking_number" not in out["matches"][0]
    assert clerk_tools.find_nearby_complaints(s, repo, PRESIDENCY, "water")["matches"] == []


def test_same_problem_is_added_to_the_original_with_one_tracking_id():
    s, repo = ready_state(), Repo()
    clerk_tools.find_nearby_complaints(s, repo, PRESIDENCY, "road")
    out = clerk_tools.file_complaint(s, repo, {}, category="road", summary_en="Potholes", place_id=PRESIDENCY,
                                     caller_confirmed=True, same_as="cv-1042")
    assert out["tracking_id"] == "CV-1042" and out["you_are_reporter_number"] == 4
    assert repo.added[0][0] == 1042 and repo.filed == []  # linked report, no second complaint


def test_linking_to_a_complaint_the_lookup_never_returned_is_refused():
    s, repo = ready_state(), Repo()
    out = clerk_tools.file_complaint(s, repo, {}, category="road", summary_en="Potholes", place_id=PRESIDENCY,
                                     caller_confirmed=True, same_as="CV-9999")
    assert out["not_filed"] and repo.added == [] and repo.filed == []


def test_status_without_a_number_finds_only_the_callers_own_complaint():
    repo = Repo()
    assert clerk_tools.get_complaint_status(repo, None, "mine", "phone")["tracking_id"] == "CV-1004"
    assert clerk_tools.get_complaint_status(repo, None, "someone-else", "phone")["found"] is False
    # on the web there is no phone number to recognise, so a tracking number is required
    assert clerk_tools.get_complaint_status(repo, None, "mine", "web")["found"] is False


def test_the_caller_hears_they_are_the_fourth_reporter(monkeypatch):
    repo = Repo()
    conv = Conversation(call_id=1, repo=repo, language="en-IN")
    offer_presidency(conv.state)
    clerk_tools.find_nearby_complaints(conv.state, repo, PRESIDENCY, "road")
    conv.state.caller_turn = 1
    conv.messages.append(Msg("model", "Potholes near Presidency University, already reported. Is that right?"))
    replies = iter([LLMReply("", [ToolCall("t1", "file_complaint", dict(
        category="road", summary_en="Potholes", place_id=PRESIDENCY, caller_confirmed=True, same_as="CV-1042"))],
        "fake", "fake", 5)])
    monkeypatch.setattr(clerk_mod.router, "generate", lambda **_: next(replies))
    result = conv.turn("Yes, that's right")
    assert "person number 4" in result.reply and "C V, 1 0, 4 2" in result.reply
    assert result.complaint == {"tracking_id": "CV-1042"}


def test_a_sensitive_report_also_makes_the_call_record_forget_the_caller():
    info = {"caller_hash": "h" * 64, "caller_last4": "1234", "channel": "phone", "call_id": 77}
    common = dict(summary_en="Someone demanded a bribe", place_id=PRESIDENCY, caller_confirmed=True)
    repo = Repo()
    clerk_tools.file_complaint(ready_state(), repo, info, category="corruption", **common)
    fields = repo.filed[0]
    assert fields["forget_call"] == 77 and fields["caller_hash"] is None and fields["caller_last4"] is None

    repo = Repo()
    clerk_tools.file_complaint(ready_state(), repo, info, category="road", **common)
    assert "forget_call" not in repo.filed[0] and repo.filed[0]["caller_hash"] == "h" * 64


def test_forgetting_the_caller_blanks_the_call_rows_hash():
    from types import SimpleNamespace

    from app.db import repo as repo_mod

    call = SimpleNamespace(caller_hash="h" * 64)
    session = SimpleNamespace(get=lambda model, i: call if i == 77 else None)
    repo_mod._forget_caller(session, 77)
    assert call.caller_hash is None
    repo_mod._forget_caller(session, None)  # nothing to forget: no lookup, no error


@pytest.mark.parametrize("category,radius", [("road", 150), ("streetlight", 150), ("drainage", 150),
                                             ("water", 500), ("electricity", 500), ("garbage", 500)])
def test_the_same_problem_radius_depends_on_the_kind_of_problem(category, radius):
    # A pothole is a point; no water is a whole street (plan E3, 18 Oct).
    asked = []

    class Spy(Repo):
        def nearby_open(self, lat, lon, category, radius_m=150):
            asked.append(radius_m)
            return []

    s = clerk_tools.ToolState()
    offer_presidency(s)
    clerk_tools.find_nearby_complaints(s, Spy(), PRESIDENCY, category)
    assert asked == [radius]
