"""Smoke test: is a running Citizen's Voice server ready for the demo? Read-only; changes nothing.

Checks the health check, public settings, complaint list, office scorecard, one complaint page
(the data and the web page) and that the live-updates stream opens. Prints a pass/fail table.

Run (from backend/):
    python -m scripts.smoke_test                                    local server
    python -m scripts.smoke_test https://<your-live-address>        the live site

Exit code 0 when nothing FAILed (WARN is allowed), 1 otherwise.
"""

import sys
import time
from dataclasses import dataclass

import httpx

DEFAULT_BASE = "http://127.0.0.1:8000"
SSE_WAIT_S = 5.0


@dataclass
class Check:
    name: str
    result: str  # PASS | WARN | FAIL | SKIP
    detail: str
    ms: int = 0


def _get(client: httpx.Client, path: str) -> tuple[httpx.Response | None, int, str]:
    t0 = time.perf_counter()
    try:
        r = client.get(path)
    except httpx.HTTPError as e:
        return None, int((time.perf_counter() - t0) * 1000), f"no answer ({type(e).__name__})"
    return r, int((time.perf_counter() - t0) * 1000), ""


def check_health(client: httpx.Client) -> Check:
    r, ms, err = _get(client, "/health")
    if r is None:
        return Check("health", "FAIL", err, ms)
    if r.status_code != 200:
        return Check("health", "FAIL", f"HTTP {r.status_code}", ms)
    body = r.json()
    if body.get("db") != "ok":
        return Check("health", "FAIL", "server up but database DOWN", ms)
    return Check("health", "PASS", f"database ok, version {body.get('version', '?')}", ms)


def check_config(client: httpx.Client) -> Check:
    r, ms, err = _get(client, "/api/config")
    if r is None or r.status_code != 200:
        return Check("config", "FAIL", err or f"HTTP {r.status_code}", ms)
    shown = r.json().get("helpline_display")
    if not shown:
        return Check("config", "WARN", "no helpline number set (VOBIZ_PHONE_NUMBER)", ms)
    return Check("config", "PASS", f"helpline {shown}", ms)


def check_complaints(client: httpx.Client) -> tuple[Check, list[dict]]:
    r, ms, err = _get(client, "/api/complaints")
    if r is None or r.status_code != 200:
        return Check("complaints list", "FAIL", err or f"HTTP {r.status_code}", ms), []
    items = r.json()
    if not isinstance(items, list):
        return Check("complaints list", "FAIL", "not a list", ms), []
    if not items:
        return Check("complaints list", "WARN", "empty: run scripts.reset_demo before the demo", ms), []
    overdue = sum(bool(c.get("overdue")) for c in items)
    return Check("complaints list", "PASS", f"{len(items)} complaints, {overdue} overdue", ms), items


def check_scorecard(client: httpx.Client) -> Check:
    r, ms, err = _get(client, "/api/scorecard")
    if r is None or r.status_code != 200:
        return Check("scorecard", "FAIL", err or f"HTTP {r.status_code}", ms)
    rows = r.json()
    if not isinstance(rows, list):
        return Check("scorecard", "FAIL", "not a list", ms)
    return Check("scorecard", "PASS" if rows else "WARN", f"{len(rows)} offices", ms)


def check_complaint_page(client: httpx.Client, items: list[dict]) -> list[Check]:
    if not items:
        return [Check("complaint data", "SKIP", "no complaints to open"),
                Check("complaint web page", "SKIP", "no complaints to open")]
    tid = items[0]["tracking_id"]
    out = []
    r, ms, err = _get(client, f"/api/complaints/{tid}")
    if r is None or r.status_code != 200:
        out.append(Check("complaint data", "FAIL", f"{tid}: " + (err or f"HTTP {r.status_code}"), ms))
    else:
        d = r.json()
        out.append(Check("complaint data", "PASS",
                         f"{tid}: {len(d.get('timeline', []))} timeline steps, {len(d.get('steps', []))} Gemma steps", ms))
    r, ms, err = _get(client, f"/c/{tid}")
    if r is None:
        out.append(Check("complaint web page", "FAIL", err, ms))
    elif r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
        out.append(Check("complaint web page", "PASS", f"/c/{tid} serves the dashboard", ms))
    elif r.status_code == 404:
        # Locally the dashboard runs on Vite (:5173); only a built app serves it from the API server.
        out.append(Check("complaint web page", "WARN", "dashboard not built into this server (npm run build)", ms))
    else:
        out.append(Check("complaint web page", "FAIL", f"HTTP {r.status_code}", ms))
    return out


def check_live_stream(client: httpx.Client, wait_s: float = SSE_WAIT_S) -> Check:
    """Opens /api/events and reads the first bytes: the server sends 'retry:' at once."""
    t0 = time.perf_counter()
    try:
        with client.stream("GET", "/api/events", timeout=httpx.Timeout(wait_s)) as r:
            ms = int((time.perf_counter() - t0) * 1000)
            if r.status_code != 200:
                return Check("live updates", "FAIL", f"HTTP {r.status_code}", ms)
            if "text/event-stream" not in r.headers.get("content-type", ""):
                return Check("live updates", "FAIL", "not an event stream", ms)
            for chunk in r.iter_text():
                if chunk.strip():
                    ok = chunk.lstrip().startswith(("retry:", "data:", ":"))
                    return Check("live updates", "PASS" if ok else "FAIL",
                                 "stream open" if ok else f"unexpected: {chunk[:40]!r}",
                                 int((time.perf_counter() - t0) * 1000))
            return Check("live updates", "FAIL", "stream closed with nothing sent", ms)
    except httpx.HTTPError as e:
        return Check("live updates", "FAIL", f"no answer ({type(e).__name__})", int((time.perf_counter() - t0) * 1000))


def run_checks(client: httpx.Client) -> list[Check]:
    checks = [check_health(client), check_config(client)]
    listed, items = check_complaints(client)
    checks += [listed, check_scorecard(client), *check_complaint_page(client, items), check_live_stream(client)]
    return checks


def table(checks: list[Check]) -> str:
    rows = [f"{'CHECK':<20} {'RESULT':<6} {'MS':>6}  DETAIL"]
    rows += [f"{c.name:<20} {c.result:<6} {c.ms:>6}  {c.detail}" for c in checks]
    failed = sum(c.result == "FAIL" for c in checks)
    rows.append("")
    rows.append(f"{'READY' if not failed else 'NOT READY'}: {failed} failed, "
                f"{sum(c.result == 'WARN' for c in checks)} warnings, {len(checks)} checks")
    return "\n".join(rows)


def main(argv: list[str] | None = None, transport: httpx.BaseTransport | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    base = (argv[0] if argv else DEFAULT_BASE).rstrip("/")
    print(f"Smoke test against {base}\n")
    with httpx.Client(base_url=base, timeout=10, transport=transport, follow_redirects=True) as client:
        checks = run_checks(client)
    print(table(checks))
    return 1 if any(c.result == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
