"""Google Maps links for a precise spot (18 Oct). Fake web: no network."""

import httpx
import pytest

from app.places import maps_link


@pytest.mark.parametrize("url,expected", [
    ("https://www.google.com/maps/place/X/@13.0045,77.5689,17z/data=!3m1!4b1!8m2!3d13.00451!4d77.57012",
     (13.00451, 77.57012)),  # the place's own point beats the map centre
    ("https://maps.google.com/?q=13.0433,77.5126", (13.0433, 77.5126)),
    ("https://www.google.com/maps/search/?api=1&query=12.97%2C77.59", (12.97, 77.59)),
    ("https://www.google.co.in/maps/@12.9716,77.5946,15z", (12.9716, 77.5946)),
    ("https://consent.google.com/ml?continue=https://www.google.com/maps/place/x/%4013.04,77.51,17z", (13.04, 77.51)),
    ("https://www.google.com/maps/place/Jayanagar", None),
])
def test_coordinates_are_read_from_every_kind_of_link(url, expected):
    assert maps_link.coords_in(url) == expected


def test_the_link_is_found_inside_the_citizens_words():
    assert maps_link.find("pothole here https://maps.app.goo.gl/AbC123. fix it") == "https://maps.app.goo.gl/AbC123"
    assert maps_link.find("at https://maps.google.com/?q=13.04,77.51") == "https://maps.google.com/?q=13.04,77.51"
    assert maps_link.find("see https://example.com/maps") is None


class Hop:
    def __init__(self, status, location=None, text=""):
        self.status_code, self.text = status, text
        self.headers = {"location": location} if location else {}
        self.is_redirect = location is not None


def test_a_short_link_is_followed_to_its_coordinates(monkeypatch):
    opened = []
    hops = {"https://maps.app.goo.gl/AbC123": Hop(302, "https://www.google.com/maps/place/X/@13.0433,77.5126,17z")}
    monkeypatch.setattr(maps_link.httpx, "get", lambda url, **k: opened.append(url) or hops[url])
    assert maps_link.location("https://maps.app.goo.gl/AbC123") == (13.0433, 77.5126)
    assert opened == ["https://maps.app.goo.gl/AbC123"]


def test_a_link_that_leads_away_from_google_is_not_followed(monkeypatch):
    opened = []
    hops = {"https://maps.app.goo.gl/evil": Hop(302, "http://169.254.169.254/latest/meta-data")}
    monkeypatch.setattr(maps_link.httpx, "get", lambda url, **k: opened.append(url) or hops[url])
    assert maps_link.location("https://maps.app.goo.gl/evil") is None
    assert opened == ["https://maps.app.goo.gl/evil"]  # the internal address was never opened


def test_a_link_that_cannot_be_opened_gives_nothing(monkeypatch):
    def down(url, **k):
        raise httpx.ConnectTimeout("slow")
    monkeypatch.setattr(maps_link.httpx, "get", down)
    assert maps_link.location("https://maps.app.goo.gl/AbC123") is None
