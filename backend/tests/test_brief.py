"""The Morning Brief: numbers by code, words by Gemma, and no number Gemma made up ever shown."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import brief, main, officer
from app.api import complaints as api
from app.llm.types import LLMError, LLMReply

client = TestClient(main.app)
NOW = datetime(2026, 10, 17, 7, 0, tzinfo=timezone.utc)


def ago(**kw):
    return (NOW - timedelta(**kw)).isoformat()


def complaint(n, **over):
    base = {"tracking_id": f"CV-{n}", "status": "open", "category": "road", "department": "bbmp",
            "summary_en": "Pothole", "urgency": 3, "is_emergency": False, "report_count": 1,
            "place_name": "Malleshwaram 8th Cross", "lat": 13.0035, "lon": 77.5710,
            "created_at": ago(hours=2), "fixed_at": None}
    return {**base, **over}


DAY = [
    complaint(1), complaint(2, lat=13.0040), complaint(3, lon=77.5715, report_count=3),  # a road cluster
    complaint(4, category="water", department="bwssb", place_name="Jayanagar", lat=12.93, lon=77.58,
              created_at=ago(days=5)),                                   # BWSSB: 2 days → overdue
    complaint(5, category="water", department="bwssb", place_name="Jayanagar", lat=12.931, lon=77.58,
              created_at=ago(days=4)),                                   # overdue
    complaint(6, department="bescom", category="electricity", is_emergency=True, lat=None, lon=None,
              place_name=None, created_at=ago(hours=5)),                 # new emergency
    complaint(7, status="fixed", created_at=ago(days=3), fixed_at=ago(hours=6)),    # fixed today
    complaint(8, status="fixed", created_at=ago(days=9), fixed_at=ago(days=2)),     # fixed earlier
]


@pytest.fixture(autouse=True)
def fresh_cache():
    brief._cache.clear()


def fake_gemma(monkeypatch, text=None, error=None):
    calls = []

    def generate(**kw):
        calls.append(kw)
        if error:
            raise error
        return LLMReply(text, [], "gemini", "gemma-4-26b-a4b-it", 800)

    monkeypatch.setattr(brief.router, "generate", generate)
    return calls


def test_the_numbers_are_computed_by_code():
    f = brief.facts(DAY, NOW)
    assert (f["new"], f["new_emergencies"], f["fixed"], f["open"], f["overdue"]) == (4, 1, 1, 6, 2)
    assert f["worst_office"] == {"office": "BWSSB (water)", "overdue": 2, "open": 2, "deadline_days": 2}
    assert f["clusters"] == [{"category": "road", "area": "Malleshwaram 8th Cross", "complaints": 3, "reports": 5}]


def test_no_overdue_means_no_worst_office_and_spread_out_complaints_are_no_cluster():
    f = brief.facts([complaint(1), complaint(2, lat=13.10)], NOW)
    assert f["worst_office"] is None and f["clusters"] == [] and f["overdue"] == 0


def test_numbers_are_found_in_digits_kannada_digits_and_words():
    assert brief.numbers_in("4 new, 1,200 calls, 2.5 days") == {"4", "1200", "2.5"}
    assert brief.numbers_in("ಇಂದು ೪ ಹೊಸ ದೂರುಗಳು") == {"4"}
    assert brief.numbers_in("Three offices, half of them, ಮೂರು ದೂರು") == {"3", "0.5"}
    assert brief.numbers_in("No numbers here at all.") == set()


def test_a_checked_gemma_brief_is_shown(monkeypatch):
    calls = fake_gemma(monkeypatch, '```json\n{"summary_en": "4 new complaints came in, 1 an emergency; 1 was fixed. '
                                    'BWSSB (water) has 2 overdue. 3 road complaints are bunched near Malleshwaram 8th Cross.", '
                                    '"summary_local": "ಇಂದು 4 ಹೊಸ ದೂರುಗಳು ಬಂದಿವೆ."}\n```')
    b = brief.morning_brief(DAY, NOW)
    assert b["source"] == "gemma" and b["summary_en"].startswith("4 new complaints")
    assert b["summary_local"] == "ಇಂದು 4 ಹೊಸ ದೂರುಗಳು ಬಂದಿವೆ." and b["rejected_numbers"] == []
    sent = calls[0]["messages"][0].text
    assert json.dumps(b["facts"]["new"]) in sent and "Malleshwaram 8th Cross" in sent


def test_gemma_invents_a_number_so_it_is_rejected_and_the_template_is_used(monkeypatch):
    # 4 new is true; "12 complaints this week" and "50%" are Gemma's own — not in the facts.
    fake_gemma(monkeypatch, '{"summary_en": "4 new today, 12 complaints this week, 50% more than usual.", '
                            '"summary_local": "ಇಂದು 4 ಹೊಸ ದೂರುಗಳು."}')
    b = brief.morning_brief(DAY, NOW)
    assert b["source"] == "template" and b["rejected_numbers"] == ["12", "50"]
    assert b["summary_en"] == brief.template(b["facts"]) and b["summary_local"] is None
    assert "12" not in b["summary_en"]


def test_a_number_written_as_a_word_is_caught_too(monkeypatch):
    fake_gemma(monkeypatch, '{"summary_en": "4 new complaints; seven offices are behind.", "summary_local": ""}')
    b = brief.morning_brief(DAY, NOW)
    assert b["source"] == "template" and b["rejected_numbers"] == ["7"]


def test_an_invented_number_in_kannada_rejects_the_whole_draft(monkeypatch):
    fake_gemma(monkeypatch, '{"summary_en": "4 new complaints today.", "summary_local": "ಇಂದು ೯ ಹೊಸ ದೂರುಗಳು."}')
    b = brief.morning_brief(DAY, NOW)
    assert b["source"] == "template" and b["rejected_numbers"] == ["9"] and b["summary_local"] is None


def test_gemma_down_or_junk_gives_the_template(monkeypatch):
    for kw in ({"error": LLMError("all providers failed")}, {"text": "Sure! Here is your brief."}):
        brief._cache.clear()
        fake_gemma(monkeypatch, **kw)
        b = brief.morning_brief(DAY, NOW)
        assert b["source"] == "template" and b["summary_en"].startswith("In the last 24 hours: 4 new complaints")


def test_the_template_only_uses_fact_numbers():
    f = brief.facts(DAY, NOW)
    assert brief.invented(brief.template(f), f) == set()
    quiet = brief.facts([], NOW)
    assert brief.template(quiet) == ("In the last 24 hours: 0 new complaints, 0 fixed. "
                                     "0 are open and 0 are past their office's deadline.")


def test_same_facts_do_not_ask_gemma_again(monkeypatch):
    calls = fake_gemma(monkeypatch, '{"summary_en": "4 new complaints today."}')
    brief.morning_brief(DAY, NOW)
    brief.morning_brief(DAY, NOW)
    assert len(calls) == 1
    brief.morning_brief(DAY + [complaint(9)], NOW)  # something changed: a new brief
    assert len(calls) == 2


def test_the_brief_is_for_signed_in_officers(monkeypatch):
    assert client.get("/api/brief").status_code == 401
    monkeypatch.setattr(officer.get_settings(), "officer_passcode", "ward-42")
    token = client.post("/api/officer/login", json={"passcode": "ward-42"}).json()["token"]
    monkeypatch.setattr(api.repo, "all_for_scorecard", lambda: [])
    fake_gemma(monkeypatch, error=LLMError("down"))
    r = client.get("/api/brief", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["facts"]["new"] == 0 and r.json()["source"] == "template"
