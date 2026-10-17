"""Build the place data once from OpenStreetMap (Overpass API), for all of Bengaluru.

Writes two files used at run time — the ONLY source of map positions for complaints:
  data/gazetteer.csv.gz  named places, landmarks, gates, and one point per ~1 km of each named road
  data/roads.json.gz     the shapes of named roads, so a pin can sit ON the road a caller names

Gates: OpenStreetMap marks most campus/hospital gates as unnamed points. Each gate on or next to a
named outline (college, school, hospital, park…) becomes "<that place> gate"; the gate closest to a
main road is the main one.

Run:  python -m scripts.build_places        (a few minutes; public Overpass servers are slow)
Data © OpenStreetMap contributors, ODbL 1.0.
"""

import csv
import gzip
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx

DATA = Path(__file__).resolve().parents[1] / "data"
SOUTH, WEST, NORTH, EAST = 12.80, 77.40, 13.30, 77.82  # Bengaluru Urban and around
TILES = 4  # 4 x 4 smaller requests: public servers refuse big ones
CACHE = Path(__file__).resolve().parents[1] / ".cache" / "overpass"  # finished tiles survive a failed run
SERVERS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
AGENT = {"User-Agent": "CitizensVoice/0.2 (hackathon; github.com/VinayG759/Citizen-s-Voice)"}

PLACE_TYPES = "suburb|neighbourhood|village|hamlet|town|locality|quarter"
AMENITIES = ("college|university|school|hospital|clinic|place_of_worship|bus_station|police|post_office|"
             "townhall|marketplace|fire_station|library|community_centre")
GATE_HOSTS = {"college", "university", "school", "hospital", "park", "stadium", "mall", "townhall"}
ROAD_TYPES = "motorway|trunk|primary|secondary|tertiary|residential|unclassified|living_street"
MAIN_ROADS = {"motorway", "trunk", "primary", "secondary", "tertiary"}
GATE_RADIUS_M = 40  # a gate this close to an outline belongs to it
# Street furniture nobody gives directions by; a clock named "Brigade" beat Brigade Road (17 Oct).
NOT_LANDMARKS = {"clock", "bench", "waste_basket", "waste_disposal", "vending_machine", "drinking_water",
                 "water_point", "toilets", "shower", "bicycle_parking", "motorcycle_parking", "parking_space",
                 "parking_entrance", "post_box", "telephone", "charging_station", "grit_bin", "shelter",
                 "fixme", "construction", "yes", "no", "roof", "hut", "shed", "garage", "garages"}


def query(bbox: str) -> str:
    return f"""
[out:json][timeout:180];
(
  node["place"~"^({PLACE_TYPES})$"]["name"]({bbox});
  nwr["amenity"~"^({AMENITIES})$"]["name"]({bbox});
  nwr["shop"="mall"]["name"]({bbox});
  nwr["leisure"~"^(park|stadium)$"]["name"]({bbox});
  nwr["railway"="station"]["name"]({bbox});
  node["highway"="bus_stop"]["name"]({bbox});
  nwr["natural"="water"]["name"]({bbox});
  nwr["water"="lake"]["name"]({bbox});
  node["barrier"~"^(gate|lift_gate|entrance)$"]({bbox});
  node["entrance"]({bbox});
);
out center tags;
way["highway"~"^({ROAD_TYPES})$"]["name"]({bbox});
out geom tags;
"""


def outline_query(bbox: str) -> str:
    # The brackets matter: without them only the LAST search's results are output (16 Oct bug:
    # only malls came back, so gates could not be matched to campuses or hospitals).
    return f"""
[out:json][timeout:180];
(
  way["name"]["amenity"~"^(college|university|school|hospital)$"]({bbox});
  way["name"]["leisure"~"^(park|stadium)$"]({bbox});
  way["name"]["shop"="mall"]({bbox});
);
out geom tags;
"""


def landmark_query(bbox: str) -> str:
    # Everything else people name a place by: "near Axis Bank", "opposite Mayura Bakery", "behind
    # Prestige apartments". Tester's report, 17 Oct: OpenStreetMap had 372 named things around
    # T. Dasarahalli; the queries above kept only a fraction of them.
    return f"""
[out:json][timeout:180];
(
  nwr["amenity"]["name"]({bbox});
  nwr["shop"]["name"]({bbox});
  nwr["office"]["name"]({bbox});
  nwr["tourism"]["name"]({bbox});
  nwr["healthcare"]["name"]({bbox});
  nwr["leisure"]["name"]({bbox});
  nwr["building"]["name"]({bbox});
  nwr["landuse"="residential"]["name"]({bbox});
);
out center tags;
"""


QUERIES = {"main": query, "outlines": outline_query, "landmarks": landmark_query}


def fetch(bbox: str, kind: str = "main") -> list[dict]:
    cached = CACHE / (("" if kind == "main" else kind + "-") + bbox.replace(",", "_") + ".json.gz")
    if cached.exists():
        with gzip.open(cached, "rt", encoding="utf-8") as f:
            return json.load(f)
    for attempt in range(4):
        for server in SERVERS:
            try:
                q = QUERIES[kind](bbox)
                r = httpx.post(server, data={"data": q}, headers=AGENT, timeout=240)
                r.raise_for_status()
                elements = r.json()["elements"]
                CACHE.mkdir(parents=True, exist_ok=True)
                with gzip.open(cached, "wt", encoding="utf-8") as f:
                    json.dump(elements, f)
                return elements
            except (httpx.HTTPError, ValueError) as e:
                code = getattr(getattr(e, "response", None), "status_code", "")
                print(f"  {server.split('/')[2]}: {type(e).__name__} {code}", file=sys.stderr)
        time.sleep(45 * (attempt + 1))
    sys.exit(f"tile {bbox} failed on every server; rerun later — finished tiles are cached")


def kind_of(tags: dict) -> str:
    for key in ("place", "amenity", "railway", "leisure", "shop", "water", "natural", "office", "tourism",
                "healthcare", "building", "landuse"):
        if key in tags:
            return "building" if tags[key] == "yes" else tags[key]  # building=yes: just "a building"
    if tags.get("highway") == "bus_stop":
        return "bus_stop"
    if "highway" in tags:
        return "road"
    return "other"


def alt_names(tags: dict) -> str:
    """Everyday and former names ('Majestic' for Kempegowda Bus Station), '|'-separated."""
    out = []
    for key in ("alt_name", "alt_name:en", "old_name", "short_name", "official_name", "loc_name", "name:kn"):
        out += [v.strip() for v in tags.get(key, "").split(";") if v.strip()]
    return "|".join(dict.fromkeys(out))


def names(tags: dict) -> tuple[str, str]:
    en = tags.get("name:en") or tags.get("name", "")
    kn = tags.get("name:kn", "")
    if not kn and any("ಀ" <= ch <= "೿" for ch in tags.get("name", "")):
        kn, en = tags["name"], tags.get("name:en", "")
    return en.strip(), kn.strip()


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat = math.radians((a[0] + b[0]) / 2)
    dx = (b[1] - a[1]) * 111_320 * math.cos(lat)
    dy = (b[0] - a[0]) * 110_540
    return math.hypot(dx, dy)


def to_segment(p, a, b) -> float:
    """Metres from point p to segment a–b (flat-earth: fine at these distances)."""
    lat = math.radians(p[0])
    kx, ky = 111_320 * math.cos(lat), 110_540
    ax, ay = (a[1] - p[1]) * kx, (a[0] - p[0]) * ky
    bx, by = (b[1] - p[1]) * kx, (b[0] - p[0]) * ky
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx, ay + t * dy)


def to_line(p, pts) -> float:
    return min((to_segment(p, pts[i], pts[i + 1]) for i in range(len(pts) - 1)), default=metres(p, pts[0]))


def simplify(pts: list[tuple[float, float]], min_m: float = 15) -> list[tuple[float, float]]:
    out = [pts[0]]
    for p in pts[1:-1]:
        if metres(out[-1], p) >= min_m:
            out.append(p)
    if len(pts) > 1:
        out.append(pts[-1])
    return [(round(a, 6), round(b, 6)) for a, b in out]


def main() -> None:
    elements: dict[str, dict] = {}
    dlat, dlon = (NORTH - SOUTH) / TILES, (EAST - WEST) / TILES
    for i in range(TILES):
        for j in range(TILES):
            bbox = f"{SOUTH + i * dlat:.4f},{WEST + j * dlon:.4f},{SOUTH + (i + 1) * dlat:.4f},{WEST + (j + 1) * dlon:.4f}"
            print(f"tile {i * TILES + j + 1}/{TILES * TILES} {bbox}", file=sys.stderr)
            for el in fetch(bbox) + fetch(bbox, "outlines") + fetch(bbox, "landmarks"):
                key = f"{el['type']}{el['id']}"
                # the same way can come back twice (centre and geometry): keep both views
                merged = elements.setdefault(key, {})
                merged.update({k: v for k, v in el.items() if v})
            time.sleep(8)

    places, seen, gates, outlines, roads = [], set(), [], [], defaultdict(list)
    for key, el in elements.items():
        tags = el.get("tags", {})
        geom = [(g["lat"], g["lon"]) for g in el.get("geometry", [])]
        if tags.get("barrier") in ("gate", "lift_gate", "entrance") or "entrance" in tags:
            if el["type"] == "node":
                gates.append((el["lat"], el["lon"]))
            continue
        en, kn = names(tags)
        if not (en or kn):
            continue
        kind = kind_of(tags)
        if kind in NOT_LANDMARKS:
            continue
        if kind == "road" and geom:
            roads[(en, kn)].append({"type": tags.get("highway", ""), "pts": simplify(geom)})
        if kind in GATE_HOSTS and len(geom) >= 3:
            outlines.append({"name_en": en, "name_kn": kn, "kind": kind, "pts": geom})
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None and geom:
            lat, lon = sum(p[0] for p in geom) / len(geom), sum(p[1] for p in geom) / len(geom)
        if lat is None:
            continue
        dedupe = (en.lower(), kn, kind, round(lat, 2), round(lon, 2))  # roads: ~one point per km
        if dedupe in seen:
            continue
        seen.add(dedupe)
        places.append({"id": f"osm-{key[0]}{el['id']}", "name_en": en, "name_kn": kn, "kind": kind,
                       "lat": round(lat, 6), "lon": round(lon, 6), "area": tags.get("addr:suburb", ""),
                       "alt": alt_names(tags)})

    # Gates: attach each to the outline it sits on; the one nearest a main road is the main gate.
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, o in enumerate(outlines):
        lats, lons = [p[0] for p in o["pts"]], [p[1] for p in o["pts"]]
        for a in range(int(min(lats) * 200), int(max(lats) * 200) + 1):
            for b in range(int(min(lons) * 200), int(max(lons) * 200) + 1):
                grid[(a, b)].append(idx)
    main_road_pts = [(p, ) for (en, kn), ways in roads.items() for w in ways if w["type"] in MAIN_ROADS
                     for p in w["pts"]]
    road_grid: dict[tuple[int, int], list] = defaultdict(list)
    for (p,) in main_road_pts:
        road_grid[(int(p[0] * 200), int(p[1] * 200))].append(p)

    def near_main_road(p) -> float:
        cell = (int(p[0] * 200), int(p[1] * 200))
        pts = [q for a in (-1, 0, 1) for b in (-1, 0, 1) for q in road_grid.get((cell[0] + a, cell[1] + b), [])]
        return min((metres(p, q) for q in pts), default=10_000)

    by_outline: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for g in gates:
        best, best_d = None, GATE_RADIUS_M
        for idx in grid.get((int(g[0] * 200), int(g[1] * 200)), []):
            d = to_line(g, outlines[idx]["pts"])
            if d <= best_d:
                best, best_d = idx, d
        if best is not None:
            by_outline[best].append(g)
    gate_rows = 0
    for idx, gs in by_outline.items():
        o = outlines[idx]
        for n, g in enumerate(sorted(gs, key=near_main_road)[:3]):
            suffix = "gate" if n == 0 else f"gate {n + 1}"
            places.append({"id": f"gate-{idx}-{n}", "name_en": f"{o['name_en']} {suffix}" if o["name_en"] else "",
                           "name_kn": f"{o['name_kn']} ಗೇಟ್" + (f" {n + 1}" if n else "") if o["name_kn"] else "",
                           "kind": "gate", "lat": round(g[0], 6), "lon": round(g[1], 6), "area": "", "alt": ""})
            gate_rows += 1

    places.sort(key=lambda r: (r["kind"], r["name_en"]))
    DATA.mkdir(exist_ok=True)
    with gzip.open(DATA / "gazetteer.csv.gz", "wt", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(places[0]))
        w.writeheader()
        w.writerows(places)
    road_list = [{"name_en": en, "name_kn": kn, "ways": [w["pts"] for w in ways]} for (en, kn), ways in roads.items()]
    with gzip.open(DATA / "roads.json.gz", "wt", encoding="utf-8") as f:
        json.dump(road_list, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {len(places)} places ({gate_rows} gates) and {len(road_list)} named roads", file=sys.stderr)


if __name__ == "__main__":
    main()
