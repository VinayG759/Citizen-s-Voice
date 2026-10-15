"""Build data/gazetteer.csv.gz once from OpenStreetMap (Overpass API).

Covers Bengaluru North (Yelahanka, Rajanukunte, Hebbal, Doddaballapur Road and around):
named places, landmarks and roads, with Kannada names where OSM has them.
Coordinates come from OpenStreetMap — this file is the ONLY source of map positions
for complaints; Gemma never invents coordinates.

Run:  python -m scripts.build_gazetteer
Data © OpenStreetMap contributors, ODbL 1.0.
"""

import csv
import gzip
import sys
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parents[1] / "data" / "gazetteer.csv.gz"
BBOX = "12.98,77.45,13.30,77.72"  # south, west, north, east
SERVERS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)

QUERY = f"""
[out:json][timeout:120];
(
  node["place"~"^(suburb|neighbourhood|village|hamlet|town|locality|quarter)$"]["name"]({BBOX});
  nwr["amenity"~"^(college|university|school|hospital|clinic|place_of_worship|bus_station|police|post_office|townhall|marketplace|fire_station|library|community_centre)$"]["name"]({BBOX});
  nwr["shop"="mall"]["name"]({BBOX});
  nwr["leisure"~"^(park|stadium)$"]["name"]({BBOX});
  nwr["railway"="station"]["name"]({BBOX});
  node["highway"="bus_stop"]["name"]({BBOX});
  way["highway"~"^(trunk|primary|secondary|tertiary|residential|unclassified)$"]["name"]({BBOX});
  nwr["natural"="water"]["name"]({BBOX});
  nwr["water"="lake"]["name"]({BBOX});
);
out center tags;
"""


def kind_of(tags: dict) -> str:
    for key in ("place", "amenity", "railway", "leisure", "shop", "water", "natural"):
        if key in tags:
            return tags[key]
    if tags.get("highway") == "bus_stop":
        return "bus_stop"
    if "highway" in tags:
        return "road"
    return "other"


def main() -> None:
    r = None
    for server in SERVERS:  # public Overpass servers are often busy; try mirrors in turn
        try:
            r = httpx.post(server, data={"data": QUERY}, timeout=180,
                           headers={"User-Agent": "CitizensVoice/0.1 (hackathon; github.com/VinayG759/Citizen-s-Voice)"})
            r.raise_for_status()
            print(f"used {server}", file=sys.stderr)
            break
        except httpx.HTTPError as e:
            print(f"{server}: {e}", file=sys.stderr)
            r = None
    if r is None:
        sys.exit("all Overpass servers failed; try again later")
    rows, seen = [], set()
    for el in r.json()["elements"]:
        tags = el.get("tags", {})
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        name_en = tags.get("name:en") or tags.get("name", "")
        name_kn = tags.get("name:kn", "")
        if not name_kn and any("ಀ" <= ch <= "೿" for ch in tags.get("name", "")):
            name_kn, name_en = tags["name"], tags.get("name:en", "")
        if not lat or not (name_en or name_kn):
            continue
        kind = kind_of(tags)
        # Roads come as many short ways with the same name: keep one point per ~1 km.
        key = (name_en.lower(), name_kn, kind, round(lat, 2), round(lon, 2))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "id": f"osm-{el['type'][0]}{el['id']}",
            "name_en": name_en.strip(),
            "name_kn": name_kn.strip(),
            "kind": kind,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "area": tags.get("addr:suburb") or tags.get("addr:city") or "",
        })
    rows.sort(key=lambda x: (x["kind"], x["name_en"]))
    OUT.parent.mkdir(exist_ok=True)
    with gzip.open(OUT, "wt", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} places to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
