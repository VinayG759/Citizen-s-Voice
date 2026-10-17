"""Emerging issues: spikes and clusters counted from fixed reports; Gemma's headline only if its numbers check out."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import emerging, main
from app.api import complaints as api
from app.llm.types import LLMError, LLMReply

client = TestClient(main.app)
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
JAYANAGAR = (12.9250, 77.5938)


def rep(n, category, hours_ago, lat=None, lon=None, area=None):
    return {"tracking_id": f"CV-{n}", "category": category, "created_at": NOW - timedelta(hours=hours_ago),
            "lat": lat, "lon": lon, "place_name": None, "area": area}


def near(dy_m, dx_m):
    return JAYANAGAR[0] + dy_m / 111_000, JAYANAGAR[1] + dx_m / 108_000


def water_spike():
    usual = [rep(1000 + i, "water", 24 * d) for i, d in enumerate((5, 12, 19, 25))]  # about one a week
    burst = [rep(1100 + i, "water", h) for i, h in enumerate((1, 3, 5, 8, 20))]  # five today
    steady = [rep(1200 + d, "road", 24 * d + 6) for d in range(26)]  # a road report every day
    return usual + burst + steady


# ---- spikes ------------------------------------------------------------------------------------

def test_a_category_far_above_its_usual_rate_is_a_spike():
    items, _ = emerging.find(water_spike(), NOW)
    spike = next(i for i in items if i.get("category") == "water")
    assert spike["reports"] == 5 and spike["window_hours"] == 24
    assert spike["usual"] == 0.2 and spike["baseline_days"] == 24
    assert spike["complaint_ids"] == ["CV-1100", "CV-1101", "CV-1102", "CV-1103", "CV-1104"]


def test_a_steady_category_is_not_a_spike():
    items, _ = emerging.find(water_spike(), NOW)
    assert not any(i.get("category") == "road" for i in items)


def test_an_area_can_spike_across_categories():
    reports = water_spike() + [rep(1300 + i, c, 2, area="Shivajinagar")
                               for i, c in enumerate(("garbage", "drainage", "noise", "garbage"))]
    items, _ = emerging.find(reports, NOW)
    area = next(i for i in items if i.get("area") == "Shivajinagar" and i["kind"] == "spike")
    assert area["reports"] == 4 and area["usual"] == 0


def test_without_history_there_are_no_spikes():
    reports = [rep(1000 + i, "water", h) for i, h in enumerate((1, 2, 3, 30, 40))]
    items, history = emerging.find(reports, NOW)
    assert history < emerging.MIN_HISTORY_DAYS and not [i for i in items if i["kind"] == "spike"]


# ---- clusters ----------------------------------------------------------------------------------

def test_different_problems_close_together_are_a_cluster():
    reports = [rep(2001, "water", 2, *near(0, 0)), rep(2002, "road", 5, *near(120, 80)),
               rep(2003, "drainage", 9, *near(-150, 60)), rep(2004, "garbage", 3, *near(5000, 0)),
               rep(2005, "water", 100, *near(10, 10))]  # older than 72 h: not counted
    clusters = emerging.clusters(reports, NOW)
    assert len(clusters) == 1
    c = clusters[0]
    assert c["reports"] == 3 and c["complaint_ids"] == ["CV-2001", "CV-2002", "CV-2003"]
    assert set(c["categories"]) == {"water", "road", "drainage"} and c["radius_m"] == 300


def test_the_same_problem_reported_three_times_is_not_a_cross_category_cluster():
    reports = [rep(3000 + i, "road", 2, *near(i * 50, 0)) for i in range(3)]
    assert emerging.clusters(reports, NOW) == []


def test_reports_are_placed_in_a_named_area():
    assert emerging.area_of(round(JAYANAGAR[0], 4), round(JAYANAGAR[1], 4))
    assert emerging.area_of(0.0, 0.0) is None  # nowhere near Bengaluru


# ---- headlines ---------------------------------------------------------------------------------

def spike_item():
    items, _ = emerging.find(water_spike(), NOW)
    return [i for i in items if i.get("category") == "water"]


def test_gemmas_headline_is_used_when_its_numbers_match(monkeypatch):
    emerging._headline_cache.clear()
    line = "Water complaints jump: 5 in the last 24 hours, against about 0.2 normally."
    monkeypatch.setattr(emerging.router, "generate", lambda **_: LLMReply('{"headlines": ["%s"]}' % line, [], "f", "f", 1))
    out = emerging.with_headlines(spike_item())
    assert out[0]["headline"] == line and out[0]["headline_by"] == "gemma"


def test_a_headline_with_a_number_not_in_the_facts_is_replaced(monkeypatch):
    emerging._headline_cache.clear()
    monkeypatch.setattr(emerging.router, "generate",
                        lambda **_: LLMReply('{"headlines": ["7 water complaints in 24 hours"]}', [], "f", "f", 1))
    out = emerging.with_headlines(spike_item())
    assert out[0]["headline_by"] == "template"
    assert out[0]["headline"] == "5 water reports in the last 24 hours (usually about 0.2)"


def test_headline_checks():
    item = {"kind": "cluster", "reports": 3, "radius_m": 300, "window_hours": 72, "complaint_ids": ["CV-1004"]}
    assert emerging.headline_ok("3 problems within 300 m in 72 hours, incl. CV-1004", item)
    assert not emerging.headline_ok("4 problems within 300 m", item)
    assert not emerging.headline_ok("3 ಸಮಸ್ಯೆಗಳು", item)  # the dashboard is in English
    assert not emerging.headline_ok("3 problems\nwithin 300 m", item)


def test_gemma_down_means_plain_headlines(monkeypatch):
    emerging._headline_cache.clear()

    def down(**_):
        raise LLMError("down")
    monkeypatch.setattr(emerging.router, "generate", down)
    out = emerging.with_headlines(spike_item())
    assert out[0]["headline_by"] == "template" and out[0]["headline"].startswith("5 water reports")


# ---- the API -----------------------------------------------------------------------------------

def test_the_api_returns_items_with_evidence(monkeypatch):
    reports = water_spike()
    monkeypatch.setattr(api.repo, "reports_since", lambda since: [dict(r) for r in reports])
    monkeypatch.setattr(emerging, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: NOW)}))
    body = client.get("/api/emerging?headlines=false").json()
    assert body["windows_hours"] == [24, 72]
    water = next(i for i in body["items"] if i.get("category") == "water")
    assert water["reports"] == 5 and water["headline_by"] == "template" and "_strength" not in water
