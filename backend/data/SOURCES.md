# Data sources

## gazetteer.csv.gz and roads.json.gz — places, gates and roads, all of Bengaluru
- Publisher: OpenStreetMap contributors
- URL: https://www.openstreetmap.org (queried via the Overpass API)
- Downloaded on: 2026-10-16
- Licence: Open Database License (ODbL) 1.0 — © OpenStreetMap contributors
- Covers: 12.80–13.30 N, 77.40–77.82 E (Bengaluru Urban and around), fetched in 16 tiles
- gazetteer.csv.gz (gzip CSV): 65,755 rows — areas, landmarks, bus stops, stations, schools,
  colleges, hospitals, places of worship, parks, lakes, one point per ~1 km of each named road,
  2350 gates, and (since 17 Oct) every other named place people give directions by: shops, banks,
  ATMs, restaurants, bakeries, pharmacies, petrol pumps, offices, apartments, named buildings and
  layouts. Street furniture (clocks, benches, bins, toilets…) is left out. 20,841 rows have a
  Kannada name; 21,916 have everyday/former names (`alt`, e.g. "Majestic" for Kempegowda Bus Station).
- Still missing: places OpenStreetMap doesn't have at all (e.g. St. Mary's Convent, T. Dasarahalli).
  For those the clerk files at the area with the landmark in words, or uses a chat location pin.
- Gates: OpenStreetMap gates are unnamed points. Each gate within 40 m of a named campus,
  hospital, school, park or mall outline is named "<that place> gate"; the one nearest a
  main road is the main gate (up to 3 per place).
- roads.json.gz: 4,298 named roads with their shapes (points every ≥15 m), used to put
  a pin ON the road a caller names.
- pincodes.json: 107 Bengaluru pincodes, each the median point of everything OpenStreetMap
  tags with that `addr:postcode` (5+ points). An optional "where" when a caller knows it.
- Rebuild: `python -m scripts.build_places` (`--pincodes` for pincodes.json only; finished tiles are cached in backend/.cache/).
