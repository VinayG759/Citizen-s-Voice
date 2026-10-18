"""What happens after filing: officer sign-in, deadlines, priority with its working, officer actions."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main, officer
from app.api import complaints as api

client = TestClient(main.app)


def complaint(**over):
    base = {"tracking_id": "CV-1004", "status": "open", "category": "road", "department": "bbmp",
            "summary_en": "Potholes", "urgency": 3, "is_emergency": False, "report_count": 1,
            "created_at": datetime.now(timezone.utc).isoformat()}
    return {**base, **over}


def days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def test_overdue_after_the_office_deadline():
    assert officer.follow_up(complaint(created_at=days_ago(3)))["overdue"] is False   # BBMP: 7 days
    late = officer.follow_up(complaint(created_at=days_ago(9)))
    assert late["overdue"] and late["escalated"] and "overdue by 2 days" in late["priority_why"]
    assert officer.follow_up(complaint(department="bescom", created_at=days_ago(3)))["overdue"]  # BESCOM: 2 days


def test_emergencies_get_one_day_and_top_priority():
    e = officer.follow_up(complaint(is_emergency=True, urgency=5, created_at=days_ago(2)))
    normal = officer.follow_up(complaint(created_at=days_ago(2)))
    assert e["overdue"] and e["priority"] > normal["priority"] and e["priority_why"].startswith("emergency")


def test_an_open_emergency_always_ranks_first(monkeypatch):
    # The case found with the demo data: a 10-day-old pothole with 4 reports scored above a fresh live wire.
    pothole = complaint(tracking_id="CV-1001", urgency=4, report_count=4, created_at=days_ago(10))
    wire = complaint(tracking_id="CV-1002", is_emergency=True, urgency=5, created_at=days_ago(0))
    fixed_wire = complaint(tracking_id="CV-1003", is_emergency=True, status="fixed", created_at=days_ago(1))
    monkeypatch.setattr(api.repo, "list_complaints", lambda *a: [pothole, fixed_wire, wire])
    order = [c["tracking_id"] for c in client.get("/api/complaints?sort=priority").json()]
    assert order == ["CV-1002", "CV-1001", "CV-1003"]


def test_fixed_complaints_drop_to_the_bottom():
    f = officer.follow_up(complaint(status="fixed", created_at=days_ago(30)))
    assert f["priority"] == 0 and not f["overdue"]


def test_passcode_sign_in(monkeypatch):
    monkeypatch.setattr(officer.get_settings(), "officer_passcode", "ward-42")
    assert client.post("/api/officer/login", json={"passcode": "wrong"}).status_code == 401
    token = client.post("/api/officer/login", json={"passcode": "ward-42"}).json()["token"]
    assert officer.token_valid(token)
    assert not officer.token_valid(token + "x") and not officer.token_valid(token[:-1] + ("0" if token[-1] != "0" else "1"))
    assert not officer.token_valid("9999999999.forged") and not officer.token_valid("")


def test_without_a_passcode_configured_nobody_can_sign_in(monkeypatch):
    monkeypatch.setattr(officer.get_settings(), "officer_passcode", "")
    assert client.post("/api/officer/login", json={"passcode": ""}).status_code == 401


def test_changing_anything_needs_an_officer():
    assert client.post("/api/complaints/CV-1004/status", json={"status": "in_progress"}).status_code == 401
    assert client.post("/api/complaints/CV-1004/route", json={"department": "bwssb"}).status_code == 401
    assert client.post("/api/complaints/CV-1004/fixed", files={"photo": ("a.jpg", b"x", "image/jpeg")}).status_code == 401
    assert client.get("/api/export.csv").status_code == 401


def test_an_officer_moves_a_complaint_along(monkeypatch):
    monkeypatch.setattr(officer.get_settings(), "officer_passcode", "ward-42")
    token = client.post("/api/officer/login", json={"passcode": "ward-42"}).json()["token"]
    seen = []
    monkeypatch.setattr(api.repo, "change_status", lambda n, st, by, note=None: seen.append((n, st, by)) or complaint(status=st))
    r = client.post("/api/complaints/CV-1004/status", json={"status": "in_progress", "note": "crew assigned"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and seen == [(1004, "in_progress", "officer")]
    # "fixed" only with a photo
    r = client.post("/api/complaints/CV-1004/status", json={"status": "fixed"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422


def test_fixed_needs_a_real_photo_and_gemma_looks_at_it(monkeypatch):
    monkeypatch.setattr(officer.get_settings(), "officer_passcode", "ward-42")
    token = client.post("/api/officer/login", json={"passcode": "ward-42"}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    monkeypatch.setattr(api.repo, "contact_for", lambda n: (None, complaint()))
    monkeypatch.setattr(api.repo, "citizen_photo", lambda n: None)
    monkeypatch.setattr(api.repo, "add_photo", lambda *a: 1)
    monkeypatch.setattr(api.repo, "change_status", lambda n, st, by, note=None: complaint(status=st))
    monkeypatch.setattr(api.vision, "check_fix", lambda p, c, b: {"looks_fixed": "yes", "reason": "Fresh asphalt"})
    assert client.post("/api/complaints/CV-1004/fixed", files={"photo": ("a.txt", b"hello", "text/plain")},
                       headers=h).status_code == 422
    r = client.post("/api/complaints/CV-1004/fixed", files={"photo": ("a.jpg", b"jpegbytes", "image/jpeg")}, headers=h)
    assert r.status_code == 200 and r.json()["gemma_verdict"]["looks_fixed"] == "yes"


def test_fixed_without_a_photo_is_allowed_and_says_so_in_the_timeline(monkeypatch):
    # 18 Oct: not every fix can be photographed (a pension paid, a bus route restored).
    monkeypatch.setattr(officer.get_settings(), "officer_passcode", "ward-42")
    token = client.post("/api/officer/login", json={"passcode": "ward-42"}).json()["token"]
    notes = []
    monkeypatch.setattr(api.repo, "contact_for", lambda n: (None, complaint()))
    monkeypatch.setattr(api.repo, "add_photo", lambda *a: pytest.fail("no photo to store"))
    monkeypatch.setattr(api.vision, "check_fix", lambda *a: pytest.fail("nothing for Gemma to check"))
    monkeypatch.setattr(api.repo, "change_status",
                        lambda n, st, by, note=None: notes.append(note) or complaint(status=st))
    r = client.post("/api/complaints/CV-1004/fixed", data={"note": "Pension paid"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["gemma_verdict"] is None
    assert notes == ["Pension paid · marked fixed without a photo"]


def test_scorecard_counts_per_office(monkeypatch):
    monkeypatch.setattr(api.repo, "all_for_scorecard", lambda: [
        complaint(created_at=days_ago(10), fixed_at=None),  # bbmp, overdue
        complaint(tracking_id="CV-1005", status="fixed", created_at=days_ago(4), fixed_at=days_ago(1)),
        complaint(tracking_id="CV-1006", department="bwssb", created_at=days_ago(1), fixed_at=None),
    ])
    rows = {r["department"]: r for r in client.get("/api/scorecard").json()}
    assert rows["bbmp"]["filed"] == 2 and rows["bbmp"]["overdue"] == 1 and rows["bbmp"]["median_days_to_fix"] == 3.0
    assert rows["bwssb"]["open"] == 1 and rows["bwssb"]["overdue"] == 0
