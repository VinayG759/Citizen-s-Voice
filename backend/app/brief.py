"""The Morning Brief: a short daily summary for officers.

Every number is computed here, by code, from the complaints. Gemma only writes the sentences around
the numbers it is given — and code then checks that every number in Gemma's text is one of those
numbers. If Gemma adds, rounds or works out a number of its own (a total, a percentage, a date), its
text is thrown away and a plain template is used instead. The AI never invents a number.

Known limit: the check catches NEW numbers, not a real number put in the wrong place (e.g. the
overdue count written as the new count). The facts are returned beside the text so anyone can compare.
"""

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone

from app import officer
from app.db.repo import _metres
from app.llm import router
from app.llm.types import LLMError, Msg
from app.vision import read_json

log = logging.getLogger(__name__)

WINDOW_HOURS = 24
CLUSTER_METRES = 300  # open complaints of one type this close together count as one area's problem
CLUSTER_MIN = 3
CACHE_SECONDS = 600  # a template (Gemma failed) is retried after this; a checked Gemma brief is kept while facts hold

SYSTEM = """You write a short morning brief for officers of a city complaints office in Bengaluru.
Use ONLY the facts given. Write every number as digits, copied exactly from the facts.
Never add, total, round or work out a number; no percentages, dates or times. Plain, calm words."""

PROMPT = """Facts (computed by code; window = last {hours} hours):
{facts}

Write 3 or 4 short sentences: what came in, what was fixed, what is overdue and the worst office,
and any area where complaints are clustering. Reply with JSON only:
{{"summary_en": "<English>", "summary_local": "<the same brief in simple Kannada, numbers as digits>"}}"""

# Numbers written as words count as numbers too.
_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "hundred": 100, "thousand": 1000, "dozen": 12, "half": 0.5, "twice": 2, "double": 2,
    "triple": 3, "ಒಂದು": 1, "ಎರಡು": 2, "ಮೂರು": 3, "ನಾಲ್ಕು": 4, "ಐದು": 5, "ಆರು": 6, "ಏಳು": 7, "ಎಂಟು": 8,
    "ಒಂಬತ್ತು": 9, "ಹತ್ತು": 10, "ನೂರು": 100, "ಸಾವಿರ": 1000,
}
# Kannada and Devanagari digits read as ordinary digits.
_DIGITS = str.maketrans("೦೧೨೩೪೫೬೭೮೯०१२३४५६७८९", "01234567890123456789")

_cache: dict = {}


# ---- the facts: code only --------------------------------------------------------------------

def _when(iso: str | None) -> datetime | None:
    if not iso:
        return None
    t = datetime.fromisoformat(iso)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _clusters(open_items: list[dict]) -> list[dict]:
    """Groups of CLUSTER_MIN+ open complaints of one type within CLUSTER_METRES of one centre complaint."""
    pts = [c for c in open_items if c.get("lat") is not None and c.get("lon") is not None]
    near = {i: {j for j, o in enumerate(pts) if o["category"] == c["category"]
                and _metres(c["lat"], c["lon"], o["lat"], o["lon"]) <= CLUSTER_METRES} for i, c in enumerate(pts)}
    left, found = set(range(len(pts))), []
    while left and len(found) < 3:
        centre = max(sorted(left), key=lambda i: len(near[i] & left))
        group = near[centre] & left
        if len(group) < CLUSTER_MIN:
            break
        found.append({"category": pts[centre]["category"], "area": pts[centre].get("place_name") or "an unnamed place",
                      "complaints": len(group), "reports": sum(pts[i].get("report_count", 1) for i in group)})
        left -= group
    return found


def facts(complaints: list[dict], now: datetime | None = None) -> dict:
    """The day's numbers, from the complaints (originals, as repo.all_for_scorecard returns them)."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=WINDOW_HOURS)
    items = [{**c, **officer.follow_up(c, now)} for c in complaints]
    new = [c for c in items if _when(c["created_at"]) >= since]
    fixed = [c for c in items if c["status"] == "fixed" and c.get("fixed_at") and _when(c["fixed_at"]) >= since]
    open_items = [c for c in items if c["status"] != "fixed"]

    by_office: dict[str, dict] = {}
    for c in open_items:
        dept = c.get("department", "unrouted")
        o = by_office.setdefault(dept, {"office": c["office"], "overdue": 0, "open": 0,
                                        "deadline_days": officer.deadline_days(dept, False)})
        o["open"] += 1
        o["overdue"] += c["overdue"]
    worst = max(by_office.values(), key=lambda o: (o["overdue"], o["open"]), default=None)

    return {
        "window_hours": WINDOW_HOURS,
        "new": len(new),
        "new_emergencies": sum(bool(c.get("is_emergency")) for c in new),
        "fixed": len(fixed),
        "open": len(open_items),
        "overdue": sum(c["overdue"] for c in open_items),
        "worst_office": worst if worst and worst["overdue"] else None,
        "clusters": _clusters(open_items),
    }


# ---- the words: Gemma, checked ------------------------------------------------------------------

def numbers_in(text: str) -> set[str]:
    """Every number in a text — digits (any script, "1,234", "2.5") and number words — as plain strings."""
    text = (text or "").translate(_DIGITS)
    found = {n.replace(",", "") for n in re.findall(r"\d+(?:[.,]\d+)*", text)}
    for token in re.split(r"[\s.,;:!?()\"'\-–—/]+", text.lower()):
        if token in _WORDS:
            found.add(str(_WORDS[token]))
    return {f[:-2] if f.endswith(".0") else f for f in found}


def invented(text: str, fact_sheet: dict) -> set[str]:
    """Numbers in Gemma's text that are not in the facts (place names count: "8th Cross" allows 8)."""
    return numbers_in(text) - numbers_in(json.dumps(fact_sheet, ensure_ascii=False))


def template(f: dict) -> str:
    """The plain brief, built by code — used whenever Gemma's text fails the number check."""
    s = (f"In the last {f['window_hours']} hours: {f['new']} new complaints"
         + (f" ({f['new_emergencies']} emergencies)" if f["new_emergencies"] else "")
         + f", {f['fixed']} fixed. {f['open']} are open and {f['overdue']} are past their office's deadline.")
    if f["worst_office"]:
        w = f["worst_office"]
        s += f" Most overdue: {w['office']}, {w['overdue']} of its {w['open']} open complaints."
    for c in f["clusters"]:
        s += f" {c['complaints']} open {c['category']} complaints are close together near {c['area']}."
    return s


def morning_brief(complaints: list[dict], now: datetime | None = None) -> dict:
    f = facts(complaints, now)
    key = json.dumps(f, sort_keys=True)
    hit = _cache.get("last")
    if hit and hit["key"] == key and (hit["result"]["source"] == "gemma" or time.time() - hit["at"] < CACHE_SECONDS):
        return hit["result"]

    result = {"facts": f, "summary_en": template(f), "summary_local": None, "source": "template",
              "numbers_checked": True, "rejected_numbers": []}
    try:
        reply = router.generate(system=SYSTEM, messages=[Msg("user", PROMPT.format(
            hours=WINDOW_HOURS, facts=json.dumps(f, ensure_ascii=False, indent=1)))], tools=[], mode="live",
            caller_language="kn-IN", max_tokens=900)
        draft = read_json(reply.text) or {}
    except LLMError as e:
        log.warning("morning brief: Gemma failed, template used: %s", e)
        draft = {}
    texts = {k: " ".join(v.split()) for k in ("summary_en", "summary_local")
             if isinstance(v := draft.get(k), str) and v.strip()}
    bad = sorted(set().union(*(invented(t, f) for t in texts.values())))
    if bad:
        # One draft, both languages: if either invents a number, neither is trusted.
        log.warning("morning brief: Gemma used numbers not in the facts %s; template used", bad)
        result["rejected_numbers"] = bad
    elif "summary_en" in texts:
        result.update(texts, source="gemma")
    _cache["last"] = {"key": key, "result": result, "at": time.time()}
    return result
