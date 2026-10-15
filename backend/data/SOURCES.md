# Data sources

## gazetteer.csv.gz — places and landmarks, Bengaluru North (gzip-compressed CSV)
- Publisher: OpenStreetMap contributors
- URL: https://www.openstreetmap.org (queried via the Overpass API)
- Downloaded on: 2026-10-16
- Licence: Open Database License (ODbL) 1.0 — © OpenStreetMap contributors
- Covers: bounding box 12.98–13.30 N, 77.45–77.72 E (Yelahanka, Rajanukunte, Hebbal,
  Doddaballapur Road, Jakkur, Kogilu and around): villages and neighbourhoods, roads,
  bus stops, stations, schools, colleges, hospitals, places of worship, parks, lakes
- Rows: 10,201 (6,245 with a Kannada name)
- Rebuild: `python -m scripts.build_gazetteer`
- Notes: road rows are one point per ~1 km of each named road (OSM splits roads into
  many short pieces). Some places have only an English or only a Kannada name.
