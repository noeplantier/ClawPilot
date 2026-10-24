"""Discovery sources behind one interface: parameters, geometry, result shape, and the local adapters. Pure: no I/O but
reading the versioned fixture file.

An adapter turns `SourceParams` into listings plus the source's raw records (for audit). Network-backed adapters take
their HTTP client as a callable, so tests never open a socket; they are only registered when
`FEATURE_EXTERNAL_SOURCES` is on. Nothing is concluded from a missing field (see signals), and every listing keeps its
source URL and licence note.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from services.outreach_os.dedupe import build_candidate, dedupe
from services.outreach_os.osm import CATEGORIES as VERTICALS
from services.outreach_os.types import RawListing

MAX_LIMIT = 100
MAX_RAW_CHARS = 4000
FIXTURE_FILE = Path(__file__).resolve().parents[2] / "fixtures" / "world" / "places.json"
EARTH_RADIUS_M = 6_371_000.0


class BadParams(ValueError):
    """The request cannot be served by this provider. The message is safe to show."""


@dataclass(frozen=True)
class SourceParams:
    vertical: str
    limit: int = 25
    country: str | None = None  # ISO 3166-1 alpha-2, upper case
    city: str | None = None  # local sources only (no geocoding is done here)
    lat: float | None = None
    lon: float | None = None
    radius_m: int = 5000

    @property
    def has_centre(self) -> bool:
        return self.lat is not None and self.lon is not None


@dataclass(frozen=True)
class RateLimit:
    per_minute: int  # per organisation and provider
    note: str  # the provider's own published limit, for the docs and the UI


@dataclass
class FetchResult:
    listings: list[RawListing]
    truncated: bool = False
    raw_sha256: str = ""
    raw_bytes: int = 0


class DiscoveryAdapter(Protocol):
    name: str
    label: str
    license_note: str
    kind: str  # "local" (no network) | "network"
    trust_absence: bool  # may a missing website be reported as "no website"? only for complete directories
    rate_limit: RateLimit
    verticals: tuple[str, ...]
    max_radius_m: int

    def fetch(self, params: SourceParams) -> FetchResult: ...


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bbox_around(lat: float, lon: float, radius_m: int) -> tuple[float, float, float, float]:
    """(south, west, north, east) of the square that contains the circle."""
    dlat = math.degrees(radius_m / EARTH_RADIUS_M)
    dlon = math.degrees(radius_m / (EARTH_RADIUS_M * max(math.cos(math.radians(lat)), 0.01)))
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


def check_params(adapter: DiscoveryAdapter, params: SourceParams) -> None:
    if params.vertical not in VERTICALS:
        raise BadParams(f"Unknown vertical: {params.vertical}")
    if params.vertical not in adapter.verticals:
        raise BadParams(f"{adapter.label} does not cover the vertical '{params.vertical}'")
    if not 1 <= params.limit <= MAX_LIMIT:
        raise BadParams(f"limit must be between 1 and {MAX_LIMIT}")
    if (params.lat is None) != (params.lon is None):
        raise BadParams("lat and lon go together")
    if params.has_centre and not 100 <= params.radius_m <= adapter.max_radius_m:
        raise BadParams(f"radius must be between 100 and {adapter.max_radius_m} metres for {adapter.label}")
    if adapter.kind == "network" and not params.has_centre:
        raise BadParams(f"{adapter.label} needs a position (lat, lon) and a radius: pick a town first")


def raw_digest(records: list[Any]) -> tuple[str, int]:
    blob = json.dumps(records, sort_keys=True, default=str, ensure_ascii=False).encode()
    return hashlib.sha256(blob).hexdigest(), len(blob)


def cap_raw(record: dict[str, Any]) -> dict[str, Any]:
    """The source's record, bounded: an oversized one is replaced by a marker rather than stored."""
    text = json.dumps(record, default=str, ensure_ascii=False)
    return record if len(text) <= MAX_RAW_CHARS else {"_truncated": True, "bytes": len(text)}


def dedupe_listings(listings: list[RawListing]) -> tuple[list[RawListing], int]:
    """One listing per business (same own domain, phone, or name + city); returns (listings, duplicates merged)."""
    merged = dedupe([build_candidate(item) for item in listings])
    return [c.listing for c in merged], len(listings) - len(merged)


def sort_by_distance(listings: list[RawListing], params: SourceParams) -> list[RawListing]:
    if not params.has_centre:
        return sorted(listings, key=lambda item: item.name.lower())
    assert params.lat is not None and params.lon is not None
    centre = (params.lat, params.lon)

    def distance(item: RawListing) -> float:
        if item.lat is None or item.lon is None:
            return float("inf")
        return haversine_m(centre[0], centre[1], item.lat, item.lon)

    return sorted(listings, key=distance)


@dataclass
class WorldFixtureAdapter:
    """Fictional businesses on every continent (demo and tests). Never touches the network; `.example` contacts only."""

    name: str = "world_fixture"
    label: str = "World demo (fictional)"
    license_note: str = "Fictional data generated for demos and tests; no real business, domains end in .example"
    kind: str = "local"
    trust_absence: bool = True
    rate_limit: RateLimit = field(default_factory=lambda: RateLimit(60, "local file, no external limit"))
    verticals: tuple[str, ...] = tuple(VERTICALS)
    max_radius_m: int = 20_000_000
    path: Path = FIXTURE_FILE

    def _records(self) -> list[dict[str, Any]]:
        return list(json.loads(self.path.read_text(encoding="utf-8"))["places"])

    def fetch(self, params: SourceParams) -> FetchResult:
        records = [r for r in self._records() if r["vertical"] == params.vertical]
        if params.country:
            records = [r for r in records if r["country"] == params.country]
        if params.city:
            records = [r for r in records if r["city"].lower() == params.city.strip().lower()]
        if params.has_centre:
            assert params.lat is not None and params.lon is not None
            records = [r for r in records if haversine_m(params.lat, params.lon, r["lat"], r["lon"]) <= params.radius_m]
        listings = [
            RawListing(
                external_id=r["external_id"],
                name=r["name"],
                source_name=self.name,
                source_url=f"fixture://world/{r['external_id']}",
                category=r["category"],
                address=r["address"],
                postcode=r["postcode"],
                city=r["city"],
                phone=r["phone"],
                email=r["email"],
                website=r["website"],
                last_updated=date.fromisoformat(r["last_updated"]),
                lat=r["lat"],
                lon=r["lon"],
                raw=cap_raw(r),
            )
            for r in records
        ]
        digest, size = raw_digest(records)
        return FetchResult(listings, truncated=False, raw_sha256=digest, raw_bytes=size)
