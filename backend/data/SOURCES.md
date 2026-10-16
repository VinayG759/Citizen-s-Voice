# Data sources

## gazetteer.csv.gz and roads.json.gz — places, gates and roads, all of Bengaluru
- Publisher: OpenStreetMap contributors
- URL: https://www.openstreetmap.org (queried via the Overpass API)
- Downloaded on: 2026-10-16
- Licence: Open Database License (ODbL) 1.0 — © OpenStreetMap contributors
- Covers: 12.80–13.30 N, 77.40–77.82 E (Bengaluru Urban and around), fetched in 16 tiles
- gazetteer.csv.gz (gzip CSV): 26,935 rows — areas, landmarks, bus stops, stations, schools,
  colleges, hospitals, places of worship, parks, lakes, one point per ~1 km of each named road,
  and 2350 gates. 16,135 rows have a Kannada name; 16,253 have everyday/former names
  (`alt`, e.g. "Majestic" for Kempegowda Bus Station).
- Gates: OpenStreetMap gates are unnamed points. Each gate within 40 m of a named campus,
  hospital, school, park or mall outline is named "<that place> gate"; the one nearest a
  main road is the main gate (up to 3 per place).
- roads.json.gz: 4,298 named roads with their shapes (points every ≥15 m), used to put
  a pin ON the road a caller names.
- Rebuild: `python -m scripts.build_places` (finished tiles are cached in backend/.cache/).
