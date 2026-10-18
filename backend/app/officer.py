"""Officers: sign-in, deadlines per office, and the rules for what happens after a complaint is filed.

Sign-in: one shared passcode (OFFICER_PASSCODE) — enough for a pilot, stated in the README. A
signed token (HMAC, 12 hours) is returned and sent back on officer requests.

Deadlines ("service levels"): each office has a number of days to act. Past it, a complaint is
OVERDUE and shown as escalated, with its priority raised — computed when read, by plain rules, so
nothing can silently drop off the list.
"""

import hashlib
import hmac
import time
from datetime import datetime, timezone

from fastapi import Header, HTTPException

from app.settings import get_settings

TOKEN_HOURS = 12

# Days each office has before a complaint counts as overdue. Emergencies: 1 day, whatever the office.
DEADLINE_DAYS = {
    "bescom": 2, "bwssb": 2, "police": 2, "traffic_police": 3, "health": 3, "bbmp": 7, "bmtc": 7,
    "food_civil_supplies": 5, "education": 7, "revenue": 15, "pollution_board": 7, "panchayat": 10,
    "lokayukta": 15, "unrouted": 3,
}
OFFICE_NAMES = {
    "bbmp": "BBMP (city corporation)", "bescom": "BESCOM (electricity)", "bwssb": "BWSSB (water)",
    "bmtc": "BMTC (buses)", "traffic_police": "Traffic Police", "police": "Police (non-emergency)",
    "health": "Health Department", "education": "Education Department",
    "food_civil_supplies": "Food & Civil Supplies (ration shops)", "revenue": "Revenue (pensions, certificates)",
    "pollution_board": "Pollution Control Board", "panchayat": "Gram Panchayat", "lokayukta": "Lokayukta (corruption)",
    "unrouted": "Not yet routed",
}


# ---- sign-in ---------------------------------------------------------------------------

def _sign(payload: str) -> str:
    key = get_settings().caller_hash_key.encode()
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()[:32]


def issue_token(passcode: str) -> str | None:
    expected = get_settings().officer_passcode
    if not expected or not hmac.compare_digest(passcode.encode(), expected.encode()):
        return None
    expires = str(int(time.time()) + TOKEN_HOURS * 3600)
    return f"{expires}.{_sign(expires)}"


def token_valid(token: str | None) -> bool:
    """Exact match only: '<expiry>.<signature>', signature checked, not expired."""
    parts = (token or "").split(".")
    if len(parts) != 2 or not parts[0].isdigit():
        return False
    expires, sig = parts
    return hmac.compare_digest(sig, _sign(expires)) and int(expires) > time.time()


def require_officer(authorization: str | None = Header(None)) -> None:
    """FastAPI dependency: officer-only routes need 'Authorization: Bearer <token>'."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token_valid(token):
        raise HTTPException(401, "officer sign-in required")


def is_officer(authorization: str | None) -> bool:
    return token_valid((authorization or "").removeprefix("Bearer ").strip())


# ---- deadlines, overdue, priority ---------------------------------------------------------

def deadline_days(department: str, is_emergency: bool) -> int:
    return 1 if is_emergency else DEADLINE_DAYS.get(department, 7)


def age_days(created_at: datetime, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    if created_at.tzinfo is None:  # the database always stores a timezone; anything else is UTC
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (now - created_at).total_seconds() / 86400


# Two kinds of emergency. Danger to life (live wire, gas leak, open manhole) comes first; a resource
# wasted by the minute (a burst water main) comes next. Both come before any ordinary complaint.
# The kind is worked out from the category, so it needs no stored field and covers older complaints too.
LOSS_CATEGORIES = ("water",)
EMERGENCY_SCORE = {"danger": 60, "loss": 45}
EMERGENCY_WHY = {"danger": "emergency: danger to life", "loss": "emergency: resource loss"}


def emergency_kind(c: dict) -> str | None:
    """"danger", "loss", or None for an ordinary complaint."""
    if not c.get("is_emergency"):
        return None
    return "loss" if c.get("category") in LOSS_CATEGORIES else "danger"


def follow_up(c: dict, now: datetime | None = None) -> dict:
    """Deadline, overdue state and priority for one public complaint dict — with the working shown,
    so anyone can see WHY it is ranked where it is (the AI never decides the order)."""
    created = datetime.fromisoformat(c["created_at"])
    age = age_days(created, now)
    days = deadline_days(c.get("department", "unrouted"), c.get("is_emergency", False))
    closed = c["status"] == "fixed"
    overdue = (not closed) and age > days
    score, why = 0, []
    kind = emergency_kind(c)
    if kind:
        score += EMERGENCY_SCORE[kind]
        why.append(EMERGENCY_WHY[kind])
    score += c.get("urgency", 3) * 5
    why.append(f"urgency {c.get('urgency', 3)}")
    if c.get("report_count", 1) > 1:
        score += (c["report_count"] - 1) * 6
        why.append(f"{c['report_count']} reports")
    score += min(int(age), 30) * 2
    why.append(f"open {int(age)} day{'s' if int(age) != 1 else ''}")
    if overdue:
        score += 25
        why.append(f"overdue by {int(age - days) or 1} day{'s' if int(age - days) > 1 else ''}")
    if c["status"] == "reopened":
        score += 20
        why.append("citizen said it was not fixed")
    if closed:
        score, why = 0, ["fixed"]
    return {
        "deadline_days": days,
        "office": OFFICE_NAMES.get(c.get("department", "unrouted"), c.get("department")),
        "overdue": overdue,
        "escalated": overdue,  # an overdue complaint is shown to the office's senior officer
        "priority": score,
        "priority_why": " · ".join(why),
        "emergency_kind": kind,
    }


def rank_key(c: dict) -> tuple[bool, int]:
    """Sort key for "most urgent first" (use with reverse=True): an open emergency always comes before
    anything else, however old or often-reported; then the priority score."""
    return (bool(c.get("is_emergency")) and c["status"] != "fixed", c["priority"])
