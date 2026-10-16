"""Find real places from what a caller said.

"Presidency University gate, Rajankunte" → the matching rows of data/gazetteer.csv.gz,
with coordinates from OpenStreetMap. This module is the only source of map
positions for complaints: Gemma proposes a place name, this code looks it up.
"""

import csv
import gzip
import math
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

GAZETTEER = Path(__file__).resolve().parents[2] / "data" / "gazetteer.csv.gz"

# Within this distance of the "area" the caller named, a match gets a boost.
NEAR_KM = 4.0
# Below this score a match is not offered at all.
MIN_SCORE = 70.0

# Words callers add that are not part of a place's name.
_FILLER = re.compile(
    r"\b(near|opposite|opp|behind|beside|next to|road|rd|main|cross|gate|stop|bus stop|the|in|at)\b|"
    r"(ಹತ್ತಿರ|ಎದುರು|ಹಿಂದೆ|ಪಕ್ಕ|ರಸ್ತೆ|ಗೇಟ್)"
)


@dataclass(frozen=True)
class Place:
    id: str
    name_en: str
    name_kn: str
    kind: str
    lat: float
    lon: float
    area: str

    @property
    def label(self) -> str:
        return self.name_en or self.name_kn


@dataclass(frozen=True)
class Match:
    place: Place
    score: float  # 0–100
    distance_km_from_area: float | None

    def as_dict(self) -> dict:
        d = asdict(self.place)
        d["score"] = round(self.score)
        if self.distance_km_from_area is not None:
            d["km_from_area"] = round(self.distance_km_from_area, 1)
        return d


def normalise(text: str) -> str:
    text = text.lower().replace(",", " ").replace(".", " ")
    text = _FILLER.sub(" ", text)
    return " ".join(text.split())


@lru_cache
def load() -> tuple[Place, ...]:
    with gzip.open(GAZETTEER, "rt", encoding="utf-8") as f:
        return tuple(
            Place(r["id"], r["name_en"], r["name_kn"], r["kind"], float(r["lat"]), float(r["lon"]), r["area"])
            for r in csv.DictReader(f)
        )


@lru_cache
def by_id() -> dict[str, Place]:
    return {p.id: p for p in load()}


def km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# Endings shared by hundreds of Karnataka place names. "Dasahalli" and "Chowdanahalli" look
# 73% alike only because of "-halli"; what tells them apart is the part before it.
_SUFFIXES = ("halli", "hally", "palya", "palaya", "pura", "puram", "nagar", "nagara", "layout",
             "kunte", "kere", "doddi", "ಹಳ್ಳಿ", "ಪಾಳ್ಯ", "ಪುರ", "ನಗರ", "ಕುಂಟೆ", "ಕೆರೆ")


def _stem(text: str) -> tuple[str, bool]:
    """'dasa halli' -> ('dasa', True). Only strips an ending if a real stem remains."""
    t = text.replace(" ", "")
    for suf in _SUFFIXES:
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[: -len(suf)], True
    return t, False


_GENERIC = {"railway", "station", "bus", "stand", "stop", "hospital", "clinic", "school", "college",
            "temple", "church", "mosque", "park", "market", "circle", "junction", "layout", "colony",
            "flyover", "bridge", "lake", "tank", "post", "office", "police", "government", "govt",
            "primary", "high", "new", "old", "town", "main", "cross", "road", "nagar", "extension"}


# Words that say what KIND of place the caller means: matching kinds get a boost.
_KIND_WORDS = {
    "station": ("station",), "railway": ("station",), "ನಿಲ್ದಾಣ": ("station", "bus_station"),
    "hospital": ("hospital", "clinic"), "ಆಸ್ಪತ್ರೆ": ("hospital", "clinic"), "clinic": ("clinic", "hospital"),
    "school": ("school",), "ಶಾಲೆ": ("school",), "college": ("college", "university"),
    "university": ("college", "university"), "ಕಾಲೇಜು": ("college",),
    "temple": ("place_of_worship",), "ದೇವಸ್ಥಾನ": ("place_of_worship",), "mosque": ("place_of_worship",),
    "church": ("place_of_worship",), "lake": ("water",), "ಕೆರೆ": ("water",), "park": ("park",),
    "bus": ("bus_stop", "bus_station"), "village": ("village", "hamlet"), "ಗ್ರಾಮ": ("village", "hamlet"),
}


def _wanted_kinds(query: str) -> set[str]:
    q = query.lower()
    return {k for word, kinds in _KIND_WORDS.items() if word in q for k in kinds}


def _score(query: str, place: Place) -> float:
    q = normalise(query)
    if not q:
        return 0.0
    best = 0.0
    for name in (place.name_en, place.name_kn):
        if not name:
            continue
        n = normalise(name)
        if len(n) < 3:  # "A Cross Road" normalises to "a": too short to match on
            continue
        # Whole-name similarity; also spelling variants: "Rajan kunte" / "Rajanukunte".
        s = max(fuzz.token_sort_ratio(q, n), fuzz.ratio(q.replace(" ", ""), n.replace(" ", "")))
        # A name found inside a longer query ("rajanukunte" in "rajanukunte railway
        # station") counts in proportion to how much of the query it explains.
        # One way only: the place name inside the caller's words, never the reverse
        # ("mary school" must not match inside "primary school").
        if 6 <= len(n) < len(q):
            coverage = len(n) / len(q)
            s = max(s, fuzz.partial_ratio(n, q) * (0.6 + 0.4 * coverage))
        # The caller said a "-halli" (or similar) name? Then the name must contain a word
        # with the same kind of ending whose part before it matches too.
        q_stem, q_has = _stem(q)
        if q_has:
            stems = [st for st, has in (_stem(w) for w in n.split()) if has]
            whole_stem, whole_has = _stem(n)
            if whole_has:
                stems.append(whole_stem)
            s = min(s, max((fuzz.ratio(q_stem, st) for st in stems), default=0) + 15)
        # Names made only of generic words ("Hospital", "Railway Station") pin down nothing,
        # even when the caller said exactly that; a real name ("Yelahanka New Town") is fine.
        if set(n.split()) <= _GENERIC and _name_counts().get(n, 0) > 1:
            s -= 15
        best = max(best, s)
    return best


@lru_cache
def _name_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in load():
        for name in {normalise(p.name_en), normalise(p.name_kn)} - {""}:
            counts[name] = counts.get(name, 0) + 1
    return counts


def find(query: str, area: str | None = None, limit: int = 3) -> list[Match]:
    """Best matches for `query`; if `area` is given, places near that area rank higher."""
    places = load()
    centre = None
    # Gemma sometimes passes the place itself as the area ("Dasahalli" near "Dasahalli"):
    # that would boost whatever matched first, right or wrong. Only a different area counts.
    if area and fuzz.ratio(normalise(area), normalise(query)) >= 85:
        area = None
    if area:
        area_hits = sorted(places, key=lambda p: _score(area, p), reverse=True)[:1]
        if area_hits and _score(area, area_hits[0]) >= 75:
            centre = area_hits[0]

    kinds = _wanted_kinds(query)
    # "The railway station" / "the hospital" + an area: the caller means the nearest one of that
    # kind in that area, not some place literally named "Railway Station".
    if centre is not None and kinds and set(normalise(query).split()) <= _GENERIC:
        near = sorted(
            (Match(p, 90.0, km_between(centre.lat, centre.lon, p.lat, p.lon)) for p in places if p.kind in kinds),
            key=lambda m: m.distance_km_from_area,
        )
        near = [m for m in near if m.distance_km_from_area <= NEAR_KM][:limit]
        if near:
            return near

    scored: list[tuple[float, Match]] = []
    for p in places:
        s = _score(query, p)
        if s < MIN_SCORE:  # bonuses below only help names that already match well
            continue
        dist = km_between(centre.lat, centre.lon, p.lat, p.lon) if centre else None
        if dist is not None:
            if dist <= NEAR_KM:
                s += 10
            elif s < 95:  # a name the caller said exactly isn't ruled out by distance
                s -= 10
        if kinds and p.kind in kinds:
            s += 8
        if p.kind == "road":
            s -= 3  # prefer a landmark over a long road with the same name
        scored.append((s, Match(p, min(s, 100.0), dist)))

    # Rank on the uncapped score, so two "100"s still come out in the right order.
    scored = [m for _, m in sorted(scored, key=lambda x: x[0], reverse=True)]
    out: list[Match] = []
    seen: set[str] = set()
    for m in scored:
        key = m.place.label.lower()
        if m.score < MIN_SCORE or key in seen:
            continue
        seen.add(key)
        out.append(m)
        if len(out) == limit:
            break
    return out
