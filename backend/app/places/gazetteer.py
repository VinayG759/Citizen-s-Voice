"""Find real places from what a caller said.

"Presidency University gate, Rajankunte" → the matching rows of data/gazetteer.csv.gz,
with coordinates from OpenStreetMap. This module is the only source of map
positions for complaints: Gemma proposes a place name, this code looks it up.
"""

import csv
import gzip
import json
import math
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

GAZETTEER = Path(__file__).resolve().parents[2] / "data" / "gazetteer.csv.gz"
PINCODES = Path(__file__).resolve().parents[2] / "data" / "pincodes.json"

# Within this distance of the "area" the caller named, a match gets a boost.
NEAR_KM = 4.0
# Below this score a match is not offered at all.
MIN_SCORE = 70.0

# Words callers add that are not part of a place's name.
_FILLER = re.compile(
    r"\b(near|opposite|opp|behind|beside|next to|road|rd|main|cross|stop|bus stop|the|in|at)\b|"
    r"(ಹತ್ತಿರ|ಎದುರು|ಹಿಂದೆ|ಪಕ್ಕ|ರಸ್ತೆ)"
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
    alt: str = ""  # everyday / former names, "|"-separated ("Majestic")

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


# Roads everyone calls by initials. OpenStreetMap spells central MG Road "Mahatma Gandhi Road", and a
# village road far west "M G Road": expanding both makes them namesakes, and the central one wins a tie.
# Only before "road": "KR Puram" is not "Krishna Rajendra Puram".
_INITIALS = {"mg": "mahatma gandhi", "kg": "kempegowda", "jc": "jayachamarajendra", "kr": "krishna rajendra"}
_INITIALS_ROAD = re.compile(r"\b(m ?g|k ?g|j ?c|k ?r)\s+(?=road\b|rd\b)")


def normalise(text: str) -> str:
    text = text.lower().replace(",", " ").replace(".", " ")
    text = _INITIALS_ROAD.sub(lambda m: _INITIALS[m.group(1).replace(" ", "")] + " ", text)
    text = _FILLER.sub(" ", text)
    return " ".join(text.split())


@lru_cache
def load() -> tuple[Place, ...]:
    with gzip.open(GAZETTEER, "rt", encoding="utf-8") as f:
        return tuple(
            Place(r["id"], r["name_en"], r["name_kn"], r["kind"], float(r["lat"]), float(r["lon"]), r["area"],
                  r.get("alt", ""))
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
            "flyover", "bridge", "lake", "tank", "post", "office", "police", "government", "govt", "gate",
            "primary", "high", "new", "old", "town", "main", "cross", "road", "nagar", "extension",
            "st", "saint", "public"}  # "St. Paul's Public School" is not "St. Mary's Public School"


# On an exact tie in score, which kind of place the caller most likely means: a suburb or town
# ("Koramangala", "Indiranagar") before a neighbourhood or village that happens to share the name.
_KIND_RANK = {"suburb": 0, "town": 0, "neighbourhood": 1, "locality": 1, "quarter": 1, "village": 1, "hamlet": 1,
              "gate": 1, "bus_stop": 3, "road": 4}

CITY_CENTRE = (12.9716, 77.5946)  # on a tie, the namesake nearer the middle of Bengaluru wins
SAME_PLACE_KM = 2.0  # two results with one name closer than this are one place; farther apart, both are shown
SAME_ROAD_KM = 4.0  # a long road is stored as several points: within this, one road is one option
# Everyday and former names ("Yelahanka Bus Station") are looser than the official name: on a tie the
# official name wins. Small enough that "Majestic" still finds Kempegowda Bus Station.
ALT_NAME_PENALTY = 4


# Words that say what KIND of place the caller means: matching kinds get a boost.
_KIND_WORDS = {
    "station": ("station",), "railway": ("station",), "ನಿಲ್ದಾಣ": ("station", "bus_station"),
    "hospital": ("hospital", "clinic"), "ಆಸ್ಪತ್ರೆ": ("hospital", "clinic"), "clinic": ("clinic", "hospital"),
    "school": ("school",), "ಶಾಲೆ": ("school",), "college": ("college", "university"),
    "university": ("college", "university"), "ಕಾಲೇಜು": ("college",),
    "temple": ("place_of_worship",), "ದೇವಸ್ಥಾನ": ("place_of_worship",), "mosque": ("place_of_worship",),
    "church": ("place_of_worship",), "lake": ("water",), "ಕೆರೆ": ("water",), "park": ("park",),
    "bus": ("bus_stop", "bus_station"), "village": ("village", "hamlet"), "ಗ್ರಾಮ": ("village", "hamlet"),
    "gate": ("gate",), "ಗೇಟ್": ("gate",),
}


def _wanted_kinds(query: str) -> set[str]:
    q = query.lower()
    return {k for word, kinds in _KIND_WORDS.items() if word in q for k in kinds}


def _score(query: str, place: Place) -> float:
    q = normalise(query)
    if not q:
        return 0.0
    # "OMG", "MIG": too short for a fuzzy match to mean anything. Only the same letters count.
    if len(q.replace(" ", "")) <= 3:
        names = (place.name_en, place.name_kn, *place.alt.split("|"))
        return 100.0 if any(normalise(n).replace(" ", "") == q.replace(" ", "") for n in names if n) else 0.0
    best = 0.0
    names = [(place.name_en, False), (place.name_kn, False), *((a, True) for a in place.alt.split("|"))]
    for name, is_alt in names:
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
        # The distinctive words must match, not just the generic ones: "Rajanukunte railway station"
        # is not "Hejjala Railway Station" just because both say "railway station".
        q_core = [w for w in q.split() if w not in _GENERIC]
        n_core = [w for w in n.split() if w not in _GENERIC]
        if q_core and n_core:
            core = max(fuzz.token_set_ratio(" ".join(q_core), " ".join(n_core)),
                       fuzz.ratio("".join(q_core), "".join(n_core)))  # "rajan kunte" = "rajanukunte"
            s = min(s, core + 20)
        # Names made only of generic words ("Hospital", "Railway Station") pin down nothing,
        # even when the caller said exactly that; a real name ("Yelahanka New Town") is fine.
        if set(n.split()) <= _GENERIC and _name_counts().get(n, 0) > 1:
            s -= 15
        best = max(best, s - (ALT_NAME_PENALTY if is_alt else 0))
    return best


@lru_cache
def _search_index() -> tuple[list[str], list[int]]:
    """Every normalised name (English and Kannada) and which place it belongs to."""
    texts, owners = [], []
    for i, p in enumerate(load()):
        for name in {normalise(p.name_en), normalise(p.name_kn), *(normalise(a) for a in p.alt.split("|"))} - {""}:
            texts.append(name)
            owners.append(i)
    return texts, owners


def _candidates(query: str, limit: int = 400) -> list[Place]:
    """A fast first pass (rapidfuzz's bulk matcher, in C) so the detailed _score only runs on
    a few hundred plausible names instead of every place in Bengaluru."""
    q = normalise(query)
    if not q:
        return []
    texts, owners = _search_index()
    places = load()
    hits = {owners[i] for scorer in (fuzz.token_set_ratio, fuzz.ratio)
            for _, _, i in process.extract(q, texts, scorer=scorer, limit=limit, score_cutoff=45)}
    return [places[i] for i in hits]


@lru_cache
def _name_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in load():
        for name in {normalise(p.name_en), normalise(p.name_kn)} - {""}:
            counts[name] = counts.get(name, 0) + 1
    return counts


def _distinctive_match(query: str, place: Place) -> float:
    """How well the caller's distinctive words ("St Mary's", not "school") appear in the place's
    names. "St. Mary's School" is fully inside "Schoenstatt St. Mary's Public School": 100."""
    q_core = [w for w in normalise(query).split() if w not in _GENERIC]
    if not q_core:
        return 0.0
    best = 0.0
    for name in (place.name_en, place.name_kn, *place.alt.split("|")):
        n_core = [w for w in normalise(name).split() if w not in _GENERIC]
        if n_core:
            best = max(best, fuzz.token_set_ratio(" ".join(q_core), " ".join(n_core)))
    return best


def area_centres(area: str) -> list[Place]:
    """Every place the area's name could mean. "Dasarahalli" is three different places in
    Bengaluru (Hebbal, Magadi Road, T. Dasarahalli): being near any of them counts as "in" it."""
    hits = [(p, _score(area, p)) for p in _candidates(area)]
    # A road is a long line, not an area: its stored point says little about where "there" is.
    hits = [h for h in hits if h[0].kind != "road"] or hits
    best = max((s for _, s in hits), default=0.0)
    if best < 75:
        return []
    return [p for p, s in hits if s >= best - 0.5]


@lru_cache
def _pincodes() -> dict[str, tuple[float, float]]:
    return {k: tuple(v) for k, v in json.loads(PINCODES.read_text(encoding="utf-8")).items()} if PINCODES.exists() else {}


def pincode_centre(pincode: str | None) -> Place | None:
    """The middle of a Bengaluru pincode, from data/pincodes.json. One we don't know is None."""
    code = "".join((pincode or "").split())
    if code not in _pincodes():
        return None
    lat, lon = _pincodes()[code]
    return Place(f"pin-{code}", code, "", "pincode", lat, lon, "")


def find(query: str, area: str | None = None, limit: int = 3, pincode: str | None = None) -> list[Match]:
    """Best matches for `query`; if `area` (or a known `pincode`) is given, places in it come first."""
    places = load()
    centres: list[Place] = []
    # Gemma sometimes passes the place itself as the area ("Dasahalli" near "Dasahalli"):
    # that would boost whatever matched first, right or wrong. Only a different area counts.
    if area and fuzz.ratio(normalise(area), normalise(query)) >= 85:
        area = None
    if area:
        centres = area_centres(area)
    # A pincode is one more "where": a shared area name ("Dasarahalli" is three places) plus the
    # caller's pincode pulls the search to the right one.
    pin = pincode_centre(pincode)
    if pin:
        centres = [c for c in centres if km_between(c.lat, c.lon, pin.lat, pin.lon) <= NEAR_KM] or [pin]

    def km_from_area(p: Place) -> float | None:
        return min(km_between(c.lat, c.lon, p.lat, p.lon) for c in centres) if centres else None

    kinds = _wanted_kinds(query)
    # "The railway station" / "the hospital" + an area: the caller means the nearest one of that
    # kind in that area, not some place literally named "Railway Station".
    if centres and kinds and set(normalise(query).split()) <= _GENERIC:
        near = sorted((Match(p, 90.0, km_from_area(p)) for p in places if p.kind in kinds),
                      key=lambda m: m.distance_km_from_area)
        near = [m for m in near if m.distance_km_from_area <= NEAR_KM][:limit]
        if near:
            return near

    scored: list[tuple[bool, float, Match]] = []
    for p in _candidates(query):
        s = _score(query, p)
        dist = km_from_area(p)
        # In the area the caller named, with the caller's distinctive words in its name: this is
        # almost certainly the place, even if its full name is longer ("Schoenstatt St. Mary's Public
        # School" for "St. Mary's School, Dasarahalli"). Real call, 17 Oct: the exact name "St. Mary's
        # School" 15 km away in Kothanur won instead.
        in_area = (dist is not None and dist <= NEAR_KM and _distinctive_match(query, p) >= 90
                   and (not kinds or p.kind in kinds or p.kind == "gate"))  # a school, not St. Mary's Church
        if s < MIN_SCORE and not in_area:  # bonuses below only help names that already match well
            continue
        if dist is not None:
            if dist <= NEAR_KM:
                s += 10
            elif s < 95:  # a name the caller said exactly isn't ruled out by distance
                s -= 10
        if kinds and p.kind in kinds:
            s += 8
        if "gate" in kinds and p.kind != "gate":
            s -= 8  # "X gate": the gate itself, not the middle of X
        if p.kind == "road":
            s -= 3  # prefer a landmark over a long road with the same name
        scored.append((in_area, s, Match(p, min(s, 100.0), dist)))

    # Places in the named area first. Then rank on the uncapped score, so two "100"s still come out
    # in the right order; on a tie, an area beats a landmark beats a bus stop beats a road, then
    # alphabetical — never by chance.
    scored = [m for _, _, m in sorted(scored, key=lambda x: (
        not x[0], -x[1], _KIND_RANK.get(x[2].place.kind, 2),
        km_between(*CITY_CENTRE, x[2].place.lat, x[2].place.lon), x[2].place.label))]
    out: list[Match] = []
    for m in scored:
        if m.score < MIN_SCORE:
            continue
        # One name, one place — unless the namesakes are far apart (two different Koramangalas).
        # A road is a long line: its points within SAME_ROAD_KM are one road.
        if any(normalise(o.place.label) == normalise(m.place.label) and
               km_between(o.place.lat, o.place.lon, m.place.lat, m.place.lon)
               < (SAME_ROAD_KM if m.place.kind == "road" else SAME_PLACE_KM) for o in out):
            continue
        out.append(m)
        if len(out) == limit:
            break
    return out


_AREA_KINDS = {"suburb", "neighbourhood", "quarter", "town", "locality"}


@lru_cache
def _areas() -> tuple[Place, ...]:
    return tuple(p for p in load() if p.kind in _AREA_KINDS and p.name_en)


WHERE_SUBURB_KM = 3.0  # a suburb this close names the spot better than a nearer, little-known neighbourhood


def where(place: Place) -> str:
    """The nearest suburb (or else neighbourhood), so a caller can tell namesakes apart:
    "the MG Road near Shivajinagar, or the one near Horamavu?"."""
    def km(a: Place) -> float:
        return km_between(a.lat, a.lon, place.lat, place.lon)
    areas = [a for a in _areas() if a.label != place.label]
    suburbs = [a for a in areas if a.kind in ("suburb", "town") and km(a) <= WHERE_SUBURB_KM]
    near = min(suburbs or areas, key=km, default=None)
    return near.label if near else ""


# ---- roads: put the pin ON the road the caller names --------------------------------------

ROADS = Path(__file__).resolve().parents[2] / "data" / "roads.json.gz"
ROAD_SNAP_M = 600  # only move the pin onto the road if that road really passes this close

_ROAD_WORDS = re.compile(r"\b(main road|road|rd|main|street|st|cross)\b|ರಸ್ತೆ")


def normalise_road(text: str) -> str:
    """'Kakolu Rd' and 'Kakolu Road' are the same road: compare without the road words."""
    t = _ROAD_WORDS.sub(" ", text.lower().replace(",", " ").replace(".", " "))
    return " ".join(t.split())


@lru_cache
def _roads() -> tuple[list[str], list[tuple[str, list]]]:
    """Normalised road names (English and Kannada), each with (display name, road shapes)."""
    if not ROADS.exists():
        return [], []
    with gzip.open(ROADS, "rt", encoding="utf-8") as f:
        data = json.load(f)
    texts, roads = [], []
    for r in data:
        for name in {normalise_road(r["name_en"]), normalise_road(r["name_kn"])} - {""}:
            texts.append(name)
            roads.append((r["name_en"] or r["name_kn"], r["ways"]))
    return texts, roads


def _nearest_on_segment(p, a, b) -> tuple[float, float, float]:
    """Closest point on segment a-b to p, and its distance in metres (flat-earth: fine under ~1 km)."""
    kx, ky = 111_320 * math.cos(math.radians(p[0])), 110_540
    ax, ay = (a[1] - p[1]) * kx, (a[0] - p[0]) * ky
    bx, by = (b[1] - p[1]) * kx, (b[0] - p[0]) * ky
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    x, y = ax + t * dx, ay + t * dy
    return p[0] + y / ky, p[1] + x / kx, math.hypot(x, y)


def snap_to_road(lat: float, lon: float, road: str) -> tuple[float, float, str, float] | None:
    """The point on the named road nearest (lat, lon): (lat, lon, road name, metres moved).
    None if no road with that name passes within ROAD_SNAP_M — then the pin stays put."""
    q = normalise_road(road)
    texts, roads = _roads()
    if not q or not texts:
        return None
    best = None
    for _, _, i in process.extract(q, texts, scorer=fuzz.ratio, limit=25, score_cutoff=80):
        name, ways = roads[i]
        for pts in ways:
            for a, b in zip(pts, pts[1:]):
                y, x, d = _nearest_on_segment((lat, lon), a, b)
                if d <= ROAD_SNAP_M and (best is None or d < best[3]):
                    best = (y, x, name, d)
    return best
