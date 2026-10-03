"""Plain value types shared by the pipeline modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class SignalState(str, Enum):
    """Never conclude a prospect is bad from a missing observation: absence of evidence is UNKNOWN."""

    UNKNOWN = "unknown"
    DETECTED = "detected"
    NOT_DETECTED = "not_detected"


@dataclass(frozen=True)
class RawListing:
    """One entry as published by a source, before normalisation. Fields are exactly what the source says."""

    external_id: str
    name: str
    source_name: str
    source_url: str
    category: str | None = None
    address: str | None = None
    postcode: str | None = None
    city: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    hours: str | None = None
    description: str | None = None
    last_updated: date | None = None
    lat: float | None = None  # WGS84, only when the source gives a position (e.g. OpenStreetMap)
    lon: float | None = None
    raw: dict[str, Any] | None = None  # the source's own record (capped), kept for audit and provenance


@dataclass(frozen=True)
class SiteSnapshot:
    """Result of looking at a prospect's homepage. `status is None` means the request itself failed."""

    url: str
    status: int | None
    html: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class SignalResult:
    key: str
    state: SignalState
    evidence: str


@dataclass
class Candidate:
    """A normalised listing plus every source that asserted it (after deduplication)."""

    listing: RawListing
    name_key: str
    domain: str | None
    phone: str | None
    email: str | None
    match_keys: list[str] = field(default_factory=list)
    merged_from: list[RawListing] = field(default_factory=list)  # the other listings folded into this one

    @property
    def all_listings(self) -> list[RawListing]:
        return [self.listing, *self.merged_from]
