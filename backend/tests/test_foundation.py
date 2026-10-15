"""Phase 0: the service answers /health honestly and reads its settings correctly."""

from fastapi.testclient import TestClient

from app import main
from app.settings import Settings

client = TestClient(main.app)


def test_health_reports_ok_when_database_is_up(monkeypatch):
    monkeypatch.setattr(main, "database_is_up", lambda: True)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["db"] == "ok"


def test_health_still_answers_when_database_is_down(monkeypatch):
    monkeypatch.setattr(main, "database_is_up", lambda: False)
    r = client.get("/health")
    assert r.status_code == 200  # the server is alive; the body says what is wrong
    assert r.json() == {"status": "degraded", "db": "down", "version": r.json()["version"]}


def test_plain_postgres_url_gets_the_psycopg_driver():
    s = Settings(_env_file=None, database_url="postgresql://u:p@host:5432/db")
    assert s.sqlalchemy_url == "postgresql+psycopg://u:p@host:5432/db"


def test_unknown_api_address_is_404_not_the_dashboard():
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404


def test_bengaluru_number_is_shown_the_local_way():
    assert main.display_phone("+918065356055") == "080 6535 6055"
    assert main.display_phone("+14155550100") == "+14155550100"  # not Bengaluru: left as-is


def test_config_exposes_only_the_helpline_number():
    r = client.get("/api/config")
    assert r.status_code == 200
    assert set(r.json()) == {"helpline_number", "helpline_display"}  # no secrets, ever
