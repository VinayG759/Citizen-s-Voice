"""Two kinds of emergency (18 Oct): danger to life first, then a resource wasted by the minute."""

from datetime import datetime, timedelta, timezone

from app import events, officer
from app.places import gazetteer
from app.tools import clerk_tools


def complaint(**kw):
    c = {"tracking_id": "CV-1001", "status": "open", "category": "road", "department": "bbmp",
         "urgency": 3, "is_emergency": False, "report_count": 1,
         "created_at": datetime.now(timezone.utc).isoformat()}
    return {**c, **kw}


def test_the_kind_comes_from_the_category():
    assert officer.emergency_kind(complaint(is_emergency=True, category="water")) == "loss"
    assert officer.emergency_kind(complaint(is_emergency=True, category="electricity")) == "danger"
    assert officer.emergency_kind(complaint(is_emergency=True, category="other")) == "danger"  # a gas leak
    assert officer.emergency_kind(complaint(category="water")) is None


def test_danger_ranks_above_loss_and_both_above_ordinary():
    danger = officer.follow_up(complaint(is_emergency=True, urgency=5, category="electricity"))
    loss = officer.follow_up(complaint(is_emergency=True, urgency=5, category="water", department="bwssb"))
    ordinary = officer.follow_up(complaint(urgency=5, report_count=3))
    assert danger["priority"] > loss["priority"] > ordinary["priority"]
    assert danger["priority_why"].startswith("emergency: danger to life")
    assert loss["priority_why"].startswith("emergency: resource loss")
    assert danger["emergency_kind"] == "danger" and loss["emergency_kind"] == "loss"
    assert ordinary["emergency_kind"] is None


def test_filing_an_emergency_alerts_every_dashboard(monkeypatch):
    sent = []
    monkeypatch.setattr(events, "publish", lambda kind, **data: sent.append((kind, data)))

    class Repo:
        def file_complaint(self, **fields):
            self.fields = fields
            return type("Filed", (), {"tracking_id": "CV-1050", "tracking_number": 1050})()

    s = clerk_tools.ToolState()
    place = gazetteer.find("Jakkur lake")[0].place
    s.offered[place.id] = clerk_tools.OfferedPlace(place, 0)
    s.caller_turn = 1
    clerk_tools.raise_emergency(s, "water main burst, water gushing onto the road")
    out = clerk_tools.file_complaint(s, Repo(), {"language": "en-IN", "channel": "web"}, category="water",
                                     summary_en="Burst water main", place_id=place.id, caller_confirmed=True)
    assert out["ok"]
    assert sent == [("emergency", {"tracking_id": "CV-1050", "emergency_kind": "loss", "place": place.label,
                                   "office": officer.OFFICE_NAMES["bwssb"], "summary": "Burst water main"})]


def test_an_ordinary_complaint_raises_no_alert(monkeypatch):
    sent = []
    monkeypatch.setattr(events, "publish", lambda kind, **data: sent.append(kind))

    class Repo:
        def file_complaint(self, **fields):
            return type("Filed", (), {"tracking_id": "CV-1051", "tracking_number": 1051})()

    s = clerk_tools.ToolState()
    place = gazetteer.find("Jakkur lake")[0].place
    s.offered[place.id] = clerk_tools.OfferedPlace(place, 0)
    s.caller_turn = 1
    clerk_tools.file_complaint(s, Repo(), {"language": "en-IN", "channel": "web"}, category="road",
                               summary_en="Pothole", place_id=place.id, caller_confirmed=True)
    assert sent == []
