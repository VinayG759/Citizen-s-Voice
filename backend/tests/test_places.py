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
    assert expected in top(query, area)


def test_gibberish_finds_nothing():
    assert g.find("asdfgh") == []


def test_a_shared_ending_alone_is_not_a_match():
    assert all("Chowdanahalli" not in m.place.label for m in g.find("Dasahalli"))


def test_a_generic_name_never_beats_the_named_place():
    # golden conversation 4 filed "Railway Station" (a bus stop literally named that) instead of Rajanukunte station
    assert top("railway station", "Rajanukunte") == "Rajanukunte"  # the station itself, nearest of its kind
    assert top("Rajanukunte railway station") == "Rajanukunte"
