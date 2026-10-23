"""Pure rules of the map search jobs: cache key, area snapping, de-duplication, error classes. No I/O, no clock."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Sequence

from services.outreach_os.types import RawListing

QUERY_VERSION = "osm-v1"  # bump when the Overpass query or its parsing changes: old cache entries stop matching
GRID = 0.005  # degrees (~500 m): neighbouring searches share one cache entry
CACHE_TTL_SECONDS = 6 * 3600
JOB_STALE_SECONDS = 180  # a job still queued/running after this was lost (instance restart): it is marked failed

STATUSES = ("queued", "running", "succeeded", "failed")
SOURCES = ("overpass", "overpass_browser", "cache")
ERROR_CODES = (
    "overpass_timeout",
    "overpass_unreachable",
    "overpass_busy",
    "overpass_bad_answer",
    "overpass_too_large",
    "job_lost",
    "internal_error",
)


@dataclass(frozen=True)
class Bbox:
    south: float
    west: float
    north: float
    east: float


def snap_bbox(box: Bbox) -> Bbox:
    """Grow the area outwards to the grid: a superset of what was asked, identical for nearby searches."""
    return Bbox(
        south=round(math.floor(box.south / GRID) * GRID, 6),
        west=round(math.floor(box.west / GRID) * GRID, 6),
        north=round(math.ceil(box.north / GRID) * GRID, 6),
        east=round(math.ceil(box.east / GRID) * GRID, 6),
    )


def cache_key(box: Bbox, category: str) -> str:
    snapped = snap_bbox(box)
    raw = f"{QUERY_VERSION}|{snapped.south:.3f},{snapped.west:.3f},{snapped.north:.3f},{snapped.east:.3f}|{category}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    letters = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", letters).strip()


def dedupe_key(item: RawListing) -> str:
    """Stable identity of a place: its source id (an OpenStreetMap node/way/relation)."""
    return f"{item.source_name}:{item.external_id}"


def loose_key(item: RawListing) -> str:
    """Same name at (almost) the same spot: OpenStreetMap often holds one place twice (a building and a point)."""
    lat = round(item.lat or 0.0, 3)
    lon = round(item.lon or 0.0, 3)
    return f"{_norm(item.name)}|{lat:.3f}|{lon:.3f}"


def dedupe(items: Iterable[RawListing]) -> list[RawListing]:
    """Keep the first of each identity; between two entries of the same spot keep the one with more published data."""
    by_id: dict[str, RawListing] = {}
    by_spot: dict[str, str] = {}
    for item in items:
        ident = dedupe_key(item)
        if ident in by_id:
            continue
        spot = loose_key(item)
        twin = by_spot.get(spot)
        if twin is not None:
            if _richness(item) > _richness(by_id[twin]):
                del by_id[twin]
                by_id[ident] = item
                by_spot[spot] = ident
            continue
        by_id[ident] = item
        by_spot[spot] = ident
    return list(by_id.values())


def _richness(item: RawListing) -> int:
    return sum(1 for v in (item.email, item.phone, item.website, item.address) if v)


def classify_failures(kinds: Sequence[str]) -> str:
    """Error code from what each server did: 'timeout', 'unreachable', 'busy' (429/5xx), 'bad_answer', 'too_large'."""
    if not kinds:
        return "overpass_unreachable"
    if "too_large" in kinds:
        return "overpass_too_large"
    if all(k == "bad_answer" for k in kinds):
        return "overpass_bad_answer"
    if "busy" in kinds:
        return "overpass_busy"
    if all(k == "timeout" for k in kinds):
        return "overpass_timeout"
    return "overpass_unreachable"


HINTS = {
    "overpass_timeout": (
        "The public OpenStreetMap servers did not answer in time. Try again in a minute, or retry from your browser."
    ),
    "overpass_unreachable": (
        "The server could not reach the OpenStreetMap servers. Retry from your browser, or see the system health page."
    ),
    "overpass_busy": "The public OpenStreetMap servers are busy (rate limit). Wait a minute, then try again.",
    "overpass_bad_answer": "A server answered with something that is not OpenStreetMap data. Try again.",
    "overpass_too_large": "The area holds too many places for one answer: zoom in.",
    "job_lost": "The search was interrupted by a server restart. Start it again.",
    "internal_error": "The search failed on our side. It has been logged; try again.",
}
