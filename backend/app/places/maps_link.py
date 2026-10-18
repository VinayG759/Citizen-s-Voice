"""A Google Maps link sent in a chat or typed in the browser: the exact spot, read from the link itself.

Full links carry the coordinates ("…/@12.97,77.59,17z", "…!3d12.97!4d77.59", "?q=12.97,77.59").
Short share links (maps.app.goo.gl/…) are opened one hop at a time until the coordinates appear, and
ONLY Google addresses are ever opened: any other host stops it, so a link can't make our server visit
an arbitrary website. Anything unreadable returns None and the clerk asks for a landmark instead.
"""

import logging
import re
from urllib.parse import unquote, urljoin, urlparse

import httpx

log = logging.getLogger(__name__)

LINK = re.compile(r"https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|maps\.google\.(?:com|co\.in)|"
                  r"(?:www\.)?google\.(?:com|co\.in)/maps)\S*", re.IGNORECASE)
_NUM = r"(-?\d{1,2}\.\d+)"
# Most exact first: the place's own point, then a searched point, then the map's centre.
_COORDS = (re.compile(rf"!3d{_NUM}!4d(-?\d{{1,3}}\.\d+)"),
           re.compile(rf"[?&/](?:q|query|ll|destination|search)[=/]{_NUM},\s*\+?(-?\d{{1,3}}\.\d+)"),
           re.compile(rf"@{_NUM},(-?\d{{1,3}}\.\d+)"))
MAX_HOPS = 5
TIMEOUT_S = 5
MAX_BODY = 500_000
AGENT = {"User-Agent": "Mozilla/5.0 (CitizensVoice; reads a shared Google Maps link)"}


def find(text: str) -> str | None:
    """The first Google Maps link in the text, if any."""
    m = LINK.search(text or "")
    return m.group(0).rstrip(".,)") if m else None


def coords_in(text: str) -> tuple[float, float] | None:
    t = unquote(unquote(text or ""))  # a consent page wraps the real link, encoded, in ?continue=
    for pattern in _COORDS:
        if m := pattern.search(t):
            lat, lon = float(m.group(1)), float(m.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
    return None


def _google(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("maps.app.goo.gl", "goo.gl") or bool(re.fullmatch(r"(?:[a-z0-9-]+\.)*google\.(?:com|co\.in)", host))


def location(url: str) -> tuple[float, float] | None:
    """The spot a Google Maps link points at, or None."""
    if found := coords_in(url):
        return found
    for _ in range(MAX_HOPS):
        if not _google(url):
            log.warning("maps link led outside Google; not followed")
            return None
        try:
            r = httpx.get(url, headers=AGENT, timeout=TIMEOUT_S, follow_redirects=False)
        except httpx.HTTPError as e:
            log.warning("maps link not opened: %s", type(e).__name__)
            return None
        if r.is_redirect and (nxt := r.headers.get("location")):
            url = urljoin(url, nxt)
            if found := coords_in(url):
                return found
            continue
        return coords_in(r.text[:MAX_BODY]) if r.status_code == 200 else None
    return None
