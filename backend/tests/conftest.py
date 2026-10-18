"""Shared test setup."""

import pytest

from app.db import repo
from app.speech import sarvam


@pytest.fixture(autouse=True)
def no_real_database_for_status_updates(monkeypatch):
    # Officer actions message chat citizens in the background (app/followup.py notify_update); without
    # this, every officer test would look them up in the real database. Tests that need it set their own.
    monkeypatch.setattr(repo, "reporter_contacts", lambda tracking_number: [])


@pytest.fixture(autouse=True)
def no_real_translation(monkeypatch):
    # A Kannada or Hindi reporter's update translates the officer's note through Sarvam (a paid call).
    # None = "couldn't translate", so the original note is sent. Tests that need it set their own.
    monkeypatch.setattr(sarvam, "translate", lambda text, target_language: None)
