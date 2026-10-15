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
        if len(n) >= 6:
            coverage = min(1.0, len(n) / len(q))
            s = max(s, fuzz.partial_ratio(n, q) * (0.6 + 0.4 * coverage))
        # Names shared by many places ("Hospital", "Railway Station") pin down nothing.
        if _name_counts().get(n, 0) > 2:
            s -= 12
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
    if area:
        area_hits = sorted(places, key=lambda p: _score(area, p), reverse=True)[:1]
        if area_hits and _score(area, area_hits[0]) >= 75:
            centre = area_hits[0]

    kinds = _wanted_kinds(query)
    scored: list[Match] = []
    for p in places:
        s = _score(query, p)
        if s < MIN_SCORE - 10:
            continue
        dist = km_between(centre.lat, centre.lon, p.lat, p.lon) if centre else None
        if dist is not None:
            s += 10 if dist <= NEAR_KM else -10
        if kinds and p.kind in kinds:
            s += 8
        if p.kind == "road":
            s -= 3  # prefer a landmark over a long road with the same name
        scored.append(Match(p, min(s, 100.0), dist))

    scored.sort(key=lambda m: m.score, reverse=True)
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
