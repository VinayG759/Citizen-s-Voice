"""Place lookup on real cases, including ones that went wrong on a real call (2026-10-16)."""

import pytest

from app.places import gazetteer as g


def top(query, area=None):
    matches = g.find(query, area)
    return matches[0].place.label if matches else None


@pytest.mark.parametrize("query,area,expected", [
    ("Dasahalli", "Dasahalli", "Dasarahalli"),  # real call: was matched to Chowdanahalli
    ("ದಾಸಹಳ್ಳಿ", None, "Dasarahalli"),
    ("St. Mary's School", "Dasarahalli", "St. Mary's School"),  # not "St Ann's" / "…Primary School"
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
