"""OpenStreetMap listings (Overpass JSON → RawListing) and the Overpass query. Pure: no I/O.

Data © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright): the attribution is part of every
result and of the recorded licence note. Only what contributors published is used; an absent tag stays absent (never
guessed), and a phone/e-mail/website is kept only if it parses.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from services.outreach_os.importer import _website
from services.outreach_os.normalize import normalize_email, normalize_phone
from services.outreach_os.types import RawListing

ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"
LICENSE_NOTE = "OpenStreetMap contributors, ODbL 1.0 — https://www.openstreetmap.org/copyright (Overpass API)"
SOURCE_NAME = "openstreetmap"
MAX_RESULTS = 300
MAX_LAT_SPAN = 0.2  # degrees (~22 km): a town, not a region
MAX_LON_SPAN = 0.3

# category → OSM tag filters (key, regex of accepted values); a category matches if any filter does.
CATEGORIES: dict[str, list[tuple[str, str]]] = {
    "restaurants": [("amenity", "^(restaurant|cafe|bar|fast_food|pub)$")],
    "bakeries": [("shop", "^(bakery|pastry|confectionery)$")],
    "beauty": [("shop", "^(hairdresser|beauty)$")],
    "hotels": [("tourism", "^(hotel|guest_house|hostel)$")],
    "shops": [("shop", ".+")],
    "crafts": [("craft", ".+")],
    "offices": [("office", "^(lawyer|accountant|estate_agent|architect|insurance|company|consulting)$")],
}


class BadArea(ValueError):
    pass


def check_area(south: float, west: float, north: float, east: float) -> None:
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise BadArea("Invalid area")
    if north - south > MAX_LAT_SPAN or east - west > MAX_LON_SPAN:
        raise BadArea("Area too large: zoom in on a town or a neighbourhood")


def build_query(south: float, west: float, north: float, east: float, category: str) -> str:
    if category not in CATEGORIES:
        raise BadArea(f"Unknown category: {category}")
    check_area(south, west, north, east)
    box = f"({south:.5f},{west:.5f},{north:.5f},{east:.5f})"
    parts = "".join(f'  nwr["{key}"~"{regex}"]["name"]{box};\n' for key, regex in CATEGORIES[category])
    return f"[out:json][timeout:25];\n(\n{parts});\nout center meta {MAX_RESULTS};"


def _first(tags: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = (tags.get(key) or "").split(";")[0].strip()
        if value:
            return value
    return None


def _date(timestamp: str | None) -> date | None:
    try:
        return date.fromisoformat((timestamp or "")[:10])
    except ValueError:
        return None


def parse_elements(payload: dict[str, Any]) -> list[RawListing]:
    """One RawListing per named element with a position; duplicates (same OSM id) collapsed."""
    out: dict[str, RawListing] = {}
    for el in payload.get("elements", []):
        tags: dict[str, str] = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        centre = el if "lat" in el else (el.get("center") or {})
        lat, lon = centre.get("lat"), centre.get("lon")
        if not name or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        kind, osm_id = el.get("type"), el.get("id")
        if kind not in ("node", "way", "relation") or not isinstance(osm_id, int):
            continue
        street = _first(tags, "addr:street")
        number = _first(tags, "addr:housenumber")
        email = normalize_email(_first(tags, "email", "contact:email"))
        phone_raw = _first(tags, "phone", "contact:phone", "contact:mobile")
        website, _ = _website(_first(tags, "website", "contact:website", "url"))
        key = f"{kind}/{osm_id}"
        out[key] = RawListing(
            external_id=key,
            name=name[:200],
            source_name=SOURCE_NAME,
            source_url=f"https://www.openstreetmap.org/{key}",
            category=_first(tags, "amenity", "shop", "craft", "office", "tourism"),
            address=" ".join(p for p in (number, street) if p) or None,
            postcode=_first(tags, "addr:postcode"),
            city=_first(tags, "addr:city"),
            phone=normalize_phone(phone_raw) and phone_raw,
            email=email,
            website=website,
            hours=_first(tags, "opening_hours"),
            description=_first(tags, "description"),
            last_updated=_date((el.get("timestamp"))),
            lat=float(lat),
            lon=float(lon),
        )
    return list(out.values())
