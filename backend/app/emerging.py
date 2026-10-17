"""Emerging issues: what is suddenly being reported more than usual, and where problems pile up.

Everything here is COUNTED by code from the reports themselves:
- a spike: a category (or an area) with many more reports in the last 24 or 72 hours than its
  usual rate over the 4 weeks before;
- a cluster: 3+ reports of different kinds within 300 m of one spot in the last 72 hours
  (a burst water main shows up as "water", "road" and "drainage" at once).
Each item carries its evidence: the counts, the area, the complaint IDs.

Gemma may phrase the one-line headline, but only from these facts: every number in its sentence
must be one of the item's numbers, otherwise the plain template sentence is used.
"""

import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from app.llm import router
from app.llm.types import LLMError, Msg
from app.places import gazetteer

log = logging.getLogger(__name__)

WINDOWS_H = (24, 72)
BASELINE_DAYS = 28
MIN_HISTORY_DAYS = 2  # less history than this: "usual" means nothing yet, so no spikes
MIN_REPORTS = 3
MIN_TIMES_USUAL = 3.0
CLUSTER_RADIUS_M = 300
CLUSTER_WINDOW_H = 72
AREA_KINDS = {"suburb", "neighbourhood", "quarter", "locality", "village", "town"}
AREA_MAX_KM = 2.5
MAX_ITEMS = 10

HEADLINE_PROMPT = """You write one-line headlines for a city officer's dashboard of emerging civic issues.
For each item below, write ONE short plain-English sentence (under 120 characters) saying what is happening.
Use ONLY the facts given. Write numbers as digits, and use only numbers that appear in that item.
No advice, no guesses about causes. Reply with JSON only: {"headlines": ["...", "..."]} in the same order."""


def _metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@lru_cache
def _areas() -> tuple[gazetteer.Place, ...]:
    return tuple(p for p in gazetteer.load() if p.kind in AREA_KINDS and p.name_en)


@lru_cache(maxsize=4096)
def area_of(lat: float, lon: float) -> str | None:
    """The nearest named neighbourhood (within 2.5 km), e.g. "Jayanagar"."""
    best, best_km = None, AREA_MAX_KM
    for p in _areas():
        km = gazetteer.km_between(lat, lon, p.lat, p.lon)
        if km < best_km:
            best, best_km = p.name_en, km
    return best


def _ids(reports: list[dict]) -> list[str]:
    return sorted({r["tracking_id"] for r in reports}, key=lambda t: int(re.sub(r"\D", "", t) or 0))


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


# ---- spikes ----------------------------------------------------------------------------------

def spikes(reports: list[dict], now: datetime) -> tuple[list[dict], float]:
    """Categories and areas reported well above their usual rate. Also returns the days of
    history the "usual" rate is based on (for the longest window)."""
    earliest = min((_aware(r["created_at"]) for r in reports), default=now)
    best: dict[tuple[str, str], dict] = {}
    history = 0.0
    for hours in WINDOWS_H:
        start = now - timedelta(hours=hours)
        base_from = max(start - timedelta(days=BASELINE_DAYS), earliest)
        history_days = (start - base_from).total_seconds() / 86400
        history = history_days
        if history_days < MIN_HISTORY_DAYS:
            continue
        groups: dict[tuple[str, str], tuple[list, list]] = {}
        for r in reports:
            t = _aware(r["created_at"])
            if t < base_from or t > now:
                continue
            keys = [("category", r["category"])]
            if r.get("area"):
                keys.append(("area", r["area"]))
            for key in keys:
                recent, base = groups.setdefault(key, ([], []))
                (recent if t >= start else base).append(r)
        for (kind, value), (recent, base) in groups.items():
            n = len(recent)
            usual = len(base) / history_days * hours / 24
            smoothed = (len(base) + 1) / history_days * hours / 24  # a first-ever report isn't a spike
            if n < MIN_REPORTS or n < MIN_TIMES_USUAL * smoothed:
                continue
            times = round(n / usual, 1) if usual else None
            item = {"kind": "spike", kind: value, "window_hours": hours, "reports": n,
                    "usual": round(usual, 1), "baseline_days": round(history_days),
                    "times_usual": times, "complaint_ids": _ids(recent),
                    "_strength": n / smoothed}
            if (kind, value) not in best or item["_strength"] > best[(kind, value)]["_strength"]:
                best[(kind, value)] = item
    return list(best.values()), round(history, 1)


# ---- clusters --------------------------------------------------------------------------------

def clusters(reports: list[dict], now: datetime) -> list[dict]:
    """Groups of 3+ recent reports, of 2+ different kinds, within 300 m of one spot. Greedy: the
    spot with the most reports around it first, then the next among what is left."""
    since = now - timedelta(hours=CLUSTER_WINDOW_H)
    pts = [r for r in reports if r.get("lat") is not None and r.get("lon") is not None
           and since <= _aware(r["created_at"]) <= now]
    pts.sort(key=lambda r: (_aware(r["created_at"]), r["tracking_id"]))  # deterministic ties
    left = list(range(len(pts)))
    out = []
    while left:
        around = {i: [j for j in left if _metres(pts[i]["lat"], pts[i]["lon"], pts[j]["lat"], pts[j]["lon"])
                      <= CLUSTER_RADIUS_M] for i in left}
        seed = max(left, key=lambda i: (len({pts[j]["category"] for j in around[i]}), len(around[i]), -i))
        members = [pts[j] for j in around[seed]]
        cats: dict[str, int] = {}
        for m in members:
            cats[m["category"]] = cats.get(m["category"], 0) + 1
        if len(members) < MIN_REPORTS or len(cats) < 2:
            break  # the best spot left isn't a cluster, so none of the rest is
        lat = sum(m["lat"] for m in members) / len(members)
        lon = sum(m["lon"] for m in members) / len(members)
        out.append({"kind": "cluster", "window_hours": CLUSTER_WINDOW_H, "reports": len(members),
                    "categories": dict(sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))),
                    "area": pts[seed].get("area") or pts[seed].get("place_name"),
                    "radius_m": CLUSTER_RADIUS_M, "centre": {"lat": round(lat, 5), "lon": round(lon, 5)},
                    "complaint_ids": _ids(members), "_strength": len(members) * len(cats)})
        left = [j for j in left if j not in set(around[seed])]
    return out


# ---- headlines -------------------------------------------------------------------------------

def template(item: dict) -> str:
    n, h = item["reports"], item["window_hours"]
    if item["kind"] == "cluster":
        where = f" near {item['area']}" if item.get("area") else ""
        kinds = ", ".join(item["categories"])
        return f"{n} reports within {item['radius_m']} m{where} in the last {h} hours: {kinds}"
    what = f"{item['category']} reports" if "category" in item else f"reports from {item['area']}"
    usual = (f"usually about {item['usual']:g}" if item["usual"] else
             f"none in the {item['baseline_days']} days before")
    return f"{n} {what} in the last {h} hours ({usual})"


def _numbers_in(value) -> set[str]:
    """Every number an item states, as it may be written ("4.0" also as "4"; CV-1004 as "1004")."""
    out: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if not k.startswith("_"):
                out |= _numbers_in(v)
    elif isinstance(value, list):
        for v in value:
            out |= _numbers_in(v)
    elif isinstance(value, bool) or value is None:
        pass
    elif isinstance(value, (int, float)):
        out.add(f"{value:g}")
        if float(value).is_integer():
            out.add(str(int(value)))
    elif isinstance(value, str):
        out |= set(re.findall(r"\d+(?:\.\d+)?", value))
    return out


def headline_ok(text: str, item: dict) -> bool:
    if not text or "\n" in text or len(text) > 140 or any(ord(ch) >= 0x250 and ch.isalpha() for ch in text):
        return False
    said = re.findall(r"\d+(?:\.\d+)?", re.sub(r"(?<=\d),(?=\d)", "", text))
    allowed = _numbers_in(item)
    return all(n in allowed or f"{float(n):g}" in allowed for n in said)


def _public(item: dict) -> dict:
    return {k: v for k, v in item.items() if not k.startswith("_")}


_headline_cache: dict[str, str] = {}


def with_headlines(items: list[dict], use_gemma: bool = True) -> list[dict]:
    facts = [_public(i) for i in items]
    keys = [json.dumps(f, sort_keys=True) for f in facts]
    todo = [i for i, k in enumerate(keys) if k not in _headline_cache]
    if use_gemma and todo:
        try:
            reply = router.generate(
                system=HEADLINE_PROMPT,
                messages=[Msg("user", json.dumps([facts[i] for i in todo], ensure_ascii=False))],
                tools=[], mode="live", caller_language="en-IN", max_tokens=600)
            m = re.search(r"\{.*\}", reply.text, re.S)
            lines = json.loads(m.group(0)).get("headlines", []) if m else []
        except (LLMError, json.JSONDecodeError, AttributeError) as e:
            log.warning("emerging headlines from Gemma failed: %s", e)
            lines = []
        if len(lines) == len(todo):
            for i, line in zip(todo, lines):
                if isinstance(line, str) and headline_ok(line.strip(), facts[i]):
                    if len(_headline_cache) > 500:
                        _headline_cache.clear()
                    _headline_cache[keys[i]] = line.strip()
    out = []
    for f, k in zip(facts, keys):
        line = _headline_cache.get(k) if use_gemma else None
        out.append({**f, "headline": line or template(f), "headline_by": "gemma" if line else "template"})
    return out


# ---- everything ------------------------------------------------------------------------------

def find(reports: list[dict], now: datetime | None = None) -> tuple[list[dict], float]:
    """Spikes and clusters, strongest first (without headlines)."""
    now = now or datetime.now(timezone.utc)
    for r in reports:
        if r.get("lat") is not None and r.get("lon") is not None and "area" not in r:
            r["area"] = area_of(round(r["lat"], 4), round(r["lon"], 4))
    found, history = spikes(reports, now)
    found += clusters(reports, now)
    found.sort(key=lambda i: -i["_strength"])
    return found[:MAX_ITEMS], history


def emerging(load_reports, now: datetime | None = None, use_gemma: bool = True) -> dict:
    now = now or datetime.now(timezone.utc)
    reports = load_reports(now - timedelta(hours=max(WINDOWS_H)) - timedelta(days=BASELINE_DAYS))
    items, history = find(reports, now)
    return {"generated_at": now.isoformat(), "windows_hours": list(WINDOWS_H), "history_days": history,
            "items": with_headlines(items, use_gemma)}
