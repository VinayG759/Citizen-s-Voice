"""Place lookup on real cases, including ones that went wrong on a real call (2026-10-16)."""

import pytest

from app.places import gazetteer as g


def top(query, area=None):
    matches = g.find(query, area)
    return matches[0].place.label if matches else None


@pytest.mark.parametrize("query,area,expected", [
    ("Dasahalli", "Dasahalli", "Dasarahalli"),  # real call: was matched to Chowdanahalli
    ("ದಾಸಹಳ್ಳಿ", None, "Dasarahalli"),
    ("Presidency University gate", "Rajankunte", "Presidency University"),
    ("Rajan kunte", None, "Rajanukunte"),
    ("ರಾಜನಕುಂಟೆ", None, "Rajanukunte"),
    ("Rajanukunte hospital", None, "Rajankunte Hospital"),
    ("Yelahanka New Town", None, "Yelahanka New Town"),
    ("Jakkur lake", None, "Jakkur Lake"),
    ("Hebbal flyover", None, "Hebbal Flyover"),
])
def test_the_right_place_comes_first(query, area, expected):
    # OpenStreetMap spells Rajanukunte two ways (village vs bus stop); both are the right place.
    assert expected in top(query, area) or (expected == "Rajanukunte" and top(query, area) == "Rajanakunte")


T_DASARAHALLI = (13.0433, 77.5126)  # Dasarahalli metro station, Tumkur Road


@pytest.mark.parametrize("query,area", [
    ("St. Mary's School", "Dasarahalli"),
    ("St Mary's Public School", "T. Dasarahalli"),
])
def test_a_school_in_the_named_area_beats_the_same_name_far_away(query, area):
    # Tester's report, 17 Oct: "St. Mary's School, Dasarahalli" pinned the St. Mary's School in Kothanur,
    # 15 km east. The real one is "Schoenstatt St. Mary's Public School", 1.4 km from the metro.
    m = g.find(query, area)[0].place
    assert "St" in m.label and "Mary" in m.label and m.kind == "school"
    assert g.km_between(m.lat, m.lon, *T_DASARAHALLI) < 2


def test_every_namesake_of_the_area_counts():
    # "Dasarahalli" is three places; the area isn't just whichever one sorts first.
    centres = g.area_centres("Dasarahalli")
    assert any(g.km_between(p.lat, p.lon, *T_DASARAHALLI) < 1 for p in centres)
    assert any(g.km_between(p.lat, p.lon, *T_DASARAHALLI) > 8 for p in centres)  # Hebbal's Dasarahalli too


def test_the_area_does_not_override_the_place_kind():
    assert all(m.place.kind != "place_of_worship" for m in g.find("St. Mary's School", "Dasarahalli")[:2])


def test_a_place_outside_the_named_area_is_not_read_back():
    from app.tools import clerk_tools
    out = clerk_tools.find_place(clerk_tools.ToolState(), "Hebbal Flyover", "Rajanukunte")
    assert out["matches"][0]["km_from_area"] > g.NEAR_KM and "Do not read these back" in out["note"]


def test_gibberish_finds_nothing():
    assert g.find("asdfgh") == []


def test_a_shared_ending_alone_is_not_a_match():
    assert all("Chowdanahalli" not in m.place.label for m in g.find("Dasahalli"))


def test_a_generic_name_never_beats_the_named_place():
    # golden conversation 4 filed "Railway Station" (a bus stop literally named that) instead of Rajanukunte station
    assert top("railway station", "Rajanukunte") == "Rajanukunte"  # the station itself, nearest of its kind
    assert top("Rajanukunte railway station") == "Rajanukunte"


def test_a_gate_pins_to_the_gate_not_the_campus_centre():
    # Real call, 16 Oct: "near the university gate" pinned in the middle of the campus.
    m = g.find("Presidency University gate", "Rajanukunte")[0].place
    assert m.kind == "gate" and m.lat > 13.171  # the Kakolu Road side, ~280 m from the centre


def test_everyday_names_work():
    assert top("Majestic") == "Kempegowda Bus Station"


def test_the_pin_can_sit_on_the_road_the_caller_names():
    from app.tools import clerk_tools
    st = clerk_tools.ToolState()
    out = clerk_tools.find_place(st, "Presidency University", "Rajanukunte", road="Kakolu Road")
    assert out["matches"][0]["name"] == "Kakolu Road near Presidency University"


@pytest.mark.parametrize("place", ["Jayanagar 4th Block", "Whitefield", "Koramangala"])
def test_all_of_bengaluru_is_covered(place):
    assert top(place) == place


# ---- places that share a name (found 17 Oct: a bare "Koramangala" pinned a village 40 km away) ----

def coords(query):
    p = g.find(query)[0].place
    return p.lat, p.lon


def test_a_bare_koramangala_is_the_suburb_not_the_village_far_away():
    lat, lon = coords("Koramangala")
    assert g.km_between(lat, lon, 12.9357, 77.6241) < 1  # the suburb, not the namesake at 13.29, 77.75


def test_a_bare_indiranagar_is_the_suburb_near_old_airport_road():
    lat, lon = coords("Indiranagar")
    assert g.km_between(lat, lon, 12.9733, 77.6405) < 1


def test_far_apart_namesakes_are_both_offered_so_the_caller_can_choose():
    named = [m for m in g.find("Koramangala", limit=5) if m.place.label == "Koramangala"]
    assert len(named) >= 2 and g.km_between(named[0].place.lat, named[0].place.lon,
                                            named[1].place.lat, named[1].place.lon) > g.SAME_PLACE_KM


def test_the_tie_order_is_always_the_same():
    assert [m.place.id for m in g.find("Koramangala")] == [m.place.id for m in g.find("Koramangala")]


def test_new_town_bus_station_is_not_the_old_town_one():
    # The Old Town station's everyday name "Yelahanka Bus Station" used to tie with the exact name.
    top = g.find("Yelahanka New Town bus station")[0].place
    assert top.label == "Yelahanka New Town" and top.kind == "bus_station"


def test_an_everyday_name_still_works_despite_the_small_penalty():
    assert "Kempegowda" in g.find("Majestic")[0].place.label


# ---- shared names and initials (found 18 Oct: "MG Road" pinned a village road at the city's western edge) ----

CENTRAL_MG_ROAD = (12.9755, 77.6068)  # MG Road metro


def test_mg_road_is_central_mg_road_first():
    p = g.find("MG Road")[0].place
    assert g.km_between(p.lat, p.lon, *CENTRAL_MG_ROAD) < 1.5


@pytest.mark.parametrize("query", ["OMG", "MIG"])
def test_a_short_query_never_fuzzy_matches_mg_road(query):
    assert all("Gandhi" not in m.place.label and "M G" not in m.place.label for m in g.find(query, limit=8))


def test_initials_expand_only_before_road():
    assert g.normalise("M.G. Road") == g.normalise("Mahatma Gandhi Road") == "mahatma gandhi"
    assert g.normalise("KR Puram") == "kr puram"


def test_one_long_road_is_one_option():
    labels = [m.place.label for m in g.find("Mahatma Gandhi Road", limit=8)
              if m.place.kind == "road" and g.km_between(m.place.lat, m.place.lon, *CENTRAL_MG_ROAD) < 4]
    assert len(labels) <= 1


def test_shared_names_are_offered_by_where_they_are():
    from app.tools import clerk_tools
    out = clerk_tools.find_place(clerk_tools.ToolState(), "MG Road")
    assert 2 <= len(out["matches"]) <= clerk_tools.OPTIONS
    assert out["matches"][0]["where"] == "Shivajinagar"
    assert len({m["where"] for m in out["matches"]}) == len(out["matches"])
    assert "match this name" in out["note"] and "near Shivajinagar" in out["note"]


def test_a_famous_suburb_is_not_questioned():
    from app.tools import clerk_tools
    out = clerk_tools.find_place(clerk_tools.ToolState(), "Koramangala")
    assert "match this name" not in out["note"]


def test_with_the_area_named_the_match_there_is_used():
    from app.tools import clerk_tools
    out = clerk_tools.find_place(clerk_tools.ToolState(), "MG Road", "Shivajinagar")
    assert out["matches"][0]["where"] == "Shivajinagar" and "match this name" not in out["note"]


# ---- optional pincode (plan E2): one more "where", never required ----

def test_a_pincode_picks_the_right_namesake():
    from app.tools import clerk_tools
    out = clerk_tools.find_place(clerk_tools.ToolState(), "Dasarahalli", pincode="560057")
    assert out["matches"][0]["km_from_area"] < 2 and "match this name" not in out["note"]
    m = g.find("Dasarahalli", pincode="560057")[0].place
    assert g.km_between(m.lat, m.lon, *T_DASARAHALLI) < 2


def test_a_pincode_works_like_an_area():
    m = g.find("St. Mary's School", pincode="560057")[0].place
    assert m.kind == "school" and g.km_between(m.lat, m.lon, *T_DASARAHALLI) < 2


@pytest.mark.parametrize("pincode", ["999999", "", None, "abc"])
def test_an_unknown_pincode_is_ignored(pincode):
    assert [m.place.id for m in g.find("MG Road", pincode=pincode)] == [m.place.id for m in g.find("MG Road")]


def test_pincode_centres_are_real():
    c = g.pincode_centre("560 001")  # spaces as a caller might say it
    assert c and g.km_between(c.lat, c.lon, *CENTRAL_MG_ROAD) < 1.5


def test_schools_sharing_the_callers_words_are_offered_not_look_alikes():
    # Tester, 18 Oct: "St. Marys Public School Road", "not Shivajinagar", and the clerk could offer no other
    # St. Mary's: the alternatives were St. Paul's and St. Thomas, and a different spelling hid the real ones.
    from app.tools import clerk_tools
    out = clerk_tools.find_place(clerk_tools.ToolState(), "St. Marys Public School Road")
    schools = [m for m in out["matches"] if m["kind"] == "school"]
    assert len(schools) >= 3 and all("Mary" in m["name"] for m in schools)
    assert len({m["where"] for m in schools}) == len(schools)
    assert "match this name" in out["note"]
