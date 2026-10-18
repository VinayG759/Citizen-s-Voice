"""Shared test setup."""

import pytest

from app.db import repo


@pytest.fixture(autouse=True)
def no_real_database_for_status_updates(monkeypatch):
    # Officer actions message chat citizens in the background (app/followup.py notify_update); without
    # this, every officer test would look them up in the real database. Tests that need it set their own.
    monkeypatch.setattr(repo, "reporter_contacts", lambda tracking_number: [])
