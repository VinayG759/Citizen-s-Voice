"""Dashboard API and live events."""

import asyncio
from datetime import datetime

from fastapi.testclient import TestClient

from app import events, main
from app.api import complaints as complaints_api
from app.db import repo
from app.db.models import Complaint

client = TestClient(main.app)


def sample(n=1004) -> Complaint:
    return Complaint(
        tracking_number=n, status="open", category="road", summary_en="Potholes", summary_local=None,
        language="kn-IN", urgency=3, is_emergency=False, is_incomplete=False, place_name="St. Mary's School",
        landmark=None, lat=13.04, lon=77.51, place_source="gazetteer", since_when="5 years", report_count=1,
        caller_hash="a" * 64, caller_last4="2659", channel="phone", created_at=datetime(2026, 10, 16, 18, 42),
    )


def test_public_view_never_contains_the_caller_hash():
    shown = repo.public_complaint(sample())
    assert "caller_hash" not in shown and shown["caller_last4"] == "2659"
    assert shown["tracking_id"] == "CV-1004"


def test_complaints_list(monkeypatch):
    monkeypatch.setattr(complaints_api.repo, "list_complaints", lambda *a: [repo.public_complaint(sample())])
    r = client.get("/api/complaints")
    assert r.status_code == 200 and r.json()[0]["place_name"] == "St. Mary's School"


def test_complaint_detail_accepts_spoken_forms_and_404s(monkeypatch):
    seen = []
    monkeypatch.setattr(complaints_api.repo, "complaint_detail", lambda n, *a: seen.append(n) or None)
    assert client.get("/api/complaints/CV-1004").status_code == 404
    assert client.get("/api/complaints/nonsense").status_code == 404
    assert seen == [1004]


def test_published_events_reach_every_open_dashboard():
    async def scenario():
        events.attach_loop(asyncio.get_running_loop())
        a, b = events.subscribe(), events.subscribe()
        events.publish("turn", call_id=5, caller="hello")
        got_a = await asyncio.wait_for(a.get(), 1)
        got_b = await asyncio.wait_for(b.get(), 1)
        events.unsubscribe(a)
        events.unsubscribe(b)
        return got_a, got_b

    got_a, got_b = asyncio.run(scenario())
    assert got_a["type"] == got_b["type"] == "turn" and got_a["caller"] == "hello"


def test_a_dashboard_that_stops_reading_is_dropped_not_waited_for():
    async def scenario():
        events.attach_loop(asyncio.get_running_loop())
        slow = events.subscribe()
        for i in range(events.MAX_QUEUE + 5):
            events.publish("turn", i=i)
        await asyncio.sleep(0.05)
        return slow in events._subscribers

    assert asyncio.run(scenario()) is False
