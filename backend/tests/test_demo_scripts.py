"""The demo scripts: the reset's safety gate and sample data, and the smoke test's verdicts.

Nothing here touches a database or the network: the reset is given a fake 'apply', the smoke test
a fake server.
"""

from datetime import datetime, timedelta, timezone

import httpx

from app import officer
from app.db.models import CATEGORIES, DEPARTMENTS, STATUSES
from app.places import gazetteer
from scripts import reset_demo, smoke_test

URL = "postgresql://demo_user:s3cret-pass@db.example-host.test:5432/postgres"
HOST = "db.example-host.test"


def _run(argv, typed="", url=URL):
    lines, applied, asked = [], [], []

    def ask(prompt):
        asked.append(prompt)
        return typed

    code = reset_demo.run(argv, database_url=url, ask=ask, out=lines.append,
                          apply=lambda *a: applied.append(a))
    return code, "\n".join(lines), applied, asked


# ---- reset_demo: the safety gate ----------------------------------------------------------

def test_default_is_a_dry_run_that_prints_the_host_and_changes_nothing():
    code, text, applied, asked = _run([])
    assert code == 0 and applied == [] and asked == []
    assert f"Database host: {HOST}" in text and "DRY RUN" in text


def test_the_password_is_never_printed():
    _, text, _, asked = _run(["--yes"], typed="wrong")
    assert "s3cret-pass" not in text and "s3cret-pass" not in "".join(asked)


def test_yes_alone_is_not_enough_the_host_must_be_typed():
    code, text, applied, asked = _run(["--yes"], typed="")
    assert code == 1 and applied == [] and len(asked) == 1 and "Nothing was changed" in text
    code, _, applied, _ = _run(["--yes"], typed="db.other-host.test")
    assert code == 1 and applied == []


def test_yes_plus_the_exact_host_resets():
    code, _, applied, _ = _run(["--yes"], typed=f"  {HOST} ")
    assert code == 0 and len(applied) == 1 and applied[0][0] is reset_demo.SEEDS


def test_no_database_url_does_nothing():
    code, text, applied, _ = _run(["--yes"], typed=HOST, url="")
    assert code == 2 and applied == [] and "not set" in text


# ---- reset_demo: the sample set is believable and consistent with the app's own rules ---------

def test_every_sample_uses_real_categories_offices_and_statuses():
    for s in reset_demo.SEEDS:
        assert s.category in CATEGORIES and s.department in DEPARTMENTS and s.status in STATUSES
        assert 1 <= s.urgency <= 5


def test_every_sample_place_comes_from_the_gazetteer():
    places = gazetteer.by_id()
    for s in reset_demo.SEEDS:
        p = places[s.place_id]
        assert (p.lat, p.lon) == (s.lat, s.lon) and p.label == s.place_name


def test_the_sample_set_covers_the_demo_story():
    now = datetime.now(timezone.utc)
    seeds = reset_demo.SEEDS
    views = [{"status": s.status, "department": s.department, "is_emergency": s.is_emergency,
              "urgency": s.urgency, "report_count": s.report_count,
              "created_at": (now - timedelta(hours=s.age_hours)).isoformat()} for s in seeds]
    overdue = [officer.follow_up(v, now)["overdue"] for v in views]
    assert sum(overdue) >= 3
    assert sum(s.is_emergency for s in seeds) == 1
    # The emergency stays inside its 1-day deadline for the rest of a demo day.
    assert all(s.age_hours < 6 for s in seeds if s.is_emergency)
    assert any(s.report_count >= 3 for s in seeds)
    assert sum(s.status == "fixed" for s in seeds) >= 2
    assert any(s.status == "reopened" for s in seeds)
    assert len({s.department for s in seeds}) >= 6


def test_duplicate_cluster_follows_the_every_third_report_rule():
    cluster = max(reset_demo.SEEDS, key=lambda s: s.report_count)
    # repo.add_report: +1 urgency at every 3rd report, from the default 3.
    assert cluster.urgency == min(5, 3 + cluster.report_count // 3)
    assert all(hours < cluster.age_hours for hours, _ in cluster.duplicates)


def test_timelines_run_forwards_and_end_in_the_current_status():
    for s in reset_demo.SEEDS:
        hours = [h for *_, h in s.history]
        assert all(h < s.age_hours for h in hours) and hours == sorted(hours, reverse=True)
        if s.history:
            assert s.history[-1][0] == s.status
        else:
            assert s.status == "open"


def test_sensitive_samples_keep_no_caller_trace():
    for s in reset_demo.SEEDS:
        if s.sensitive:
            assert s.caller_last4 is None and not s.duplicates


# ---- smoke_test ---------------------------------------------------------------------------------

COMPLAINT = {"tracking_id": "CV-1001", "overdue": True}


def fake_server(health=None, complaints=(COMPLAINT,), page_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json=health or {"status": "ok", "db": "ok", "version": "0.1.0"})
        if path == "/api/config":
            return httpx.Response(200, json={"helpline_number": "+918065356055", "helpline_display": "080 6535 6055"})
        if path == "/api/complaints":
            return httpx.Response(200, json=list(complaints))
        if path == "/api/scorecard":
            return httpx.Response(200, json=[{"department": "bbmp"}])
        if path == "/api/complaints/CV-1001":
            return httpx.Response(200, json={"timeline": [{}, {}], "steps": []})
        if path == "/c/CV-1001":
            return httpx.Response(page_status, text="<!doctype html>", headers={"content-type": "text/html"})
        if path == "/api/events":
            return httpx.Response(200, content=b"retry: 3000\n\n", headers={"content-type": "text/event-stream"})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_a_healthy_server_passes_everything(capsys):
    assert smoke_test.main(["http://demo.test"], transport=fake_server()) == 0
    out = capsys.readouterr().out
    assert "READY: 0 failed" in out and "FAIL" not in out.split("READY")[0]


def test_database_down_fails():
    with httpx.Client(base_url="http://demo.test", transport=fake_server(health={"status": "degraded", "db": "down"})) as c:
        assert smoke_test.check_health(c).result == "FAIL"


def test_an_empty_database_warns_and_skips_the_complaint_page(capsys):
    assert smoke_test.main(["http://demo.test"], transport=fake_server(complaints=())) == 0
    out = capsys.readouterr().out
    assert "reset_demo" in out and "SKIP" in out


def test_dashboard_not_built_is_a_warning_not_a_failure():
    with httpx.Client(base_url="http://demo.test", transport=fake_server(page_status=404)) as c:
        checks = smoke_test.check_complaint_page(c, [COMPLAINT])
    assert [ch.result for ch in checks] == ["PASS", "WARN"]


def test_an_unreachable_server_fails_every_check(capsys):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    assert smoke_test.main(["http://demo.test"], transport=httpx.MockTransport(refuse)) == 1
    assert "NOT READY" in capsys.readouterr().out
