"""Status updates to chat citizens (18 Oct: Telegram citizens hear about every change; phone and browser
citizens are called once, after the fix). Fake database, fake Telegram. No network."""

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import followup, main, officer
from app.api import complaints as api
from app.contact import seal
from app.settings import get_settings


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setattr(get_settings(), "contact_encryption_key", Fernet.generate_key().decode())


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setitem(followup._chat_notifiers, "telegram", lambda chat_id, text: out.append((chat_id, text)))
    return out


def test_every_chat_reporter_hears_of_an_update_but_phone_callers_are_not_messaged(monkeypatch, sent):
    monkeypatch.setattr(followup.repo, "reporter_contacts", lambda n: [
        (seal("telegram", "111"), True, "en-IN"), (seal("phone", "+919845012345"), False, "kn-IN"),
        (seal("telegram", "222"), False, "kn-IN")])
    followup.notify_update(1013, "in_progress", "Crew sent, work starts Monday")
    assert sent == [("111", "Update on CV-1013: work on your complaint has started. Officer's note: Crew sent, work starts Monday"),
                    ("222", "CV-1013 ಬಗ್ಗೆ update: ನಿಮ್ಮ complaint ಮೇಲೆ ಕೆಲಸ ಶುರು ಆಗಿದೆ. Officer note: Crew sent, work starts Monday")]


def test_on_fixed_the_first_reporter_gets_the_question_instead_so_only_the_others_get_a_message(monkeypatch, sent):
    monkeypatch.setattr(followup.repo, "reporter_contacts", lambda n: [
        (seal("telegram", "111"), True, "en-IN"), (seal("telegram", "222"), False, "en-IN")])
    followup.notify_update(1013, "fixed")
    assert sent == [("222", "Update on CV-1013: the officer has marked it fixed.")]


def test_a_message_that_cannot_be_sent_never_stops_the_others(monkeypatch):
    out = []

    def flaky(chat_id, text):
        if chat_id == "111":
            raise RuntimeError("Telegram down")
        out.append(chat_id)

    monkeypatch.setitem(followup._chat_notifiers, "telegram", flaky)
    monkeypatch.setattr(followup.repo, "reporter_contacts", lambda n: [
        (seal("telegram", "111"), True, "en-IN"), (seal("telegram", "222"), False, "en-IN")])
    followup.notify_update(1013, "reopened")
    assert out == ["222"]


def test_re_routing_names_the_new_office():
    text = followup.update_text("routed", 1013, "hi-IN", office="BWSSB (water)")
    assert "BWSSB (water)" in text and "CV-1013" in text


def test_the_officer_starting_work_sends_the_update(monkeypatch):
    calls = []
    monkeypatch.setattr(officer.get_settings(), "officer_passcode", "ward-42")
    monkeypatch.setattr(api.repo, "change_status", lambda n, st, by, note=None: {
        "tracking_id": f"CV-{n}", "status": st, "created_at": "2026-10-18T04:13:53+00:00", "department": "bwssb"})
    monkeypatch.setattr(followup, "notify_update", lambda *a: calls.append(a))
    client = TestClient(main.app)
    token = client.post("/api/officer/login", json={"passcode": "ward-42"}).json()["token"]
    r = client.post("/api/complaints/CV-1013/status", json={"status": "in_progress", "note": "Crew sent"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert calls == [(1013, "in_progress", "Crew sent", None)]
