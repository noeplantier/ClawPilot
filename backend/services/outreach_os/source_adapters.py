"""Network-backed discovery adapters (OpenStreetMap, French company registry). The HTTP client is injected: pure
otherwise.

Both are free, keyless and official/open data. Anything else (Google Places, SerpAPI, Bing, Apollo, Clearbit,
Crunchbase) is deliberately not here: see docs/sources.md for why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from services.outreach_os import osm
from services.outreach_os.discovery import (
    FetchResult,
    RateLimit,
    SourceParams,
    bbox_around,
    cap_raw,
    haversine_m,
    raw_digest,
)
from services.outreach_os.types import RawListing

# Vertical → NAF rev. 2 codes accepted by the registry search; a vertical with no entry is not offered by that provider.
NAF_BY_VERTICAL: dict[str, str] = {
    "restaurants": "56.10A,56.10B,56.10C,56.30Z",
    "bakeries": "10.71C,10.71D,47.24Z",
    "beauty": "96.02A,96.02B",
    "hotels": "55.10Z,55.20Z",
    "offices": "69.10Z,69.20Z,68.31Z,71.11Z",
}
REGISTRY_PAGE = 25


@dataclass
class OsmAdapter:
    fetch_json: Callable[[str], dict[str, Any]]
    name: str = osm.SOURCE_NAME
    label: str = "OpenStreetMap (Overpass)"
    license_note: str = osm.LICENSE_NOTE
    kind: str = "network"
    trust_absence: bool = False  # an empty tag in OSM is not proof that nothing exists
    rate_limit: RateLimit = field(
        default_factory=lambda: RateLimit(6, "public Overpass servers: keep it light (cached 10 min)")
    )
    verticals: tuple[str, ...] = tuple(osm.CATEGORIES)
    max_radius_m: int = 10_000

    def fetch(self, params: SourceParams) -> FetchResult:
        assert params.lat is not None and params.lon is not None
        south, west, north, east = bbox_around(params.lat, params.lon, params.radius_m)
        query = osm.build_query(south, west, north, east, params.vertical)
        payload = self.fetch_json(query)
        elements = payload.get("elements", [])
        by_id = {f"{e.get('type')}/{e.get('id')}": e for e in elements}
        listings = []
        for item in osm.parse_elements(payload):
            if item.lat is None or item.lon is None:
                continue
            if haversine_m(params.lat, params.lon, item.lat, item.lon) > params.radius_m:
                continue  # the query is a square: keep the circle that was asked for
            tags = (by_id.get(item.external_id) or {}).get("tags") or {}
            raw = cap_raw({"osm": item.external_id, "tags": {k: str(v)[:200] for k, v in list(tags.items())[:40]}})
            listings.append(RawListing(**{**item.__dict__, "raw": raw}))
        digest, size = raw_digest(elements)
        return FetchResult(listings, truncated=len(elements) >= osm.MAX_RESULTS, raw_sha256=digest, raw_bytes=size)


@dataclass
class FrenchRegistryAdapter:
    """recherche-entreprises.api.gouv.fr: official open data on French companies (SIREN, head office address, activity).

    It publishes no e-mail, phone or website: those stay empty ("unknown"), never guessed."""

    fetch_page: Callable[[dict[str, Any]], dict[str, Any]]
    name: str = "registry_fr"
    label: str = "French company registry (open data)"
    license_note: str = "Licence Ouverte 2.0 (Etalab) — recherche-entreprises.api.gouv.fr, Annuaire des Entreprises"
    kind: str = "network"
    trust_absence: bool = False
    rate_limit: RateLimit = field(default_factory=lambda: RateLimit(10, "7 requests/second per IP (provider limit)"))
    verticals: tuple[str, ...] = tuple(NAF_BY_VERTICAL)
    max_radius_m: int = 50_000

    def fetch(self, params: SourceParams) -> FetchResult:
        assert params.lat is not None and params.lon is not None
        pages = -(-params.limit // REGISTRY_PAGE)
        results: list[dict[str, Any]] = []
        total = 0
        for page in range(1, pages + 1):
            data = self.fetch_page(
                {
                    "lat": params.lat,
                    "long": params.lon,
                    "radius": max(1, round(params.radius_m / 1000)),
                    "activite_principale": NAF_BY_VERTICAL[params.vertical],
                    "etat_administratif": "A",
                    "per_page": REGISTRY_PAGE,
                    "page": page,
                }
            )
            batch = data.get("results") or []
            total = int(data.get("total_results") or 0)
            results += batch
            if len(batch) < REGISTRY_PAGE:
                break
        listings = [item for item in (_listing(r, self.name) for r in results) if item is not None][: params.limit]
        digest, size = raw_digest(results)
        return FetchResult(listings, truncated=total > len(results), raw_sha256=digest, raw_bytes=size)


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _listing(record: dict[str, Any], source: str) -> RawListing | None:
    siren = str(record.get("siren") or "").strip()
    name = str(record.get("nom_complet") or record.get("nom_raison_sociale") or "").strip()
    seat = record.get("siege") or {}
    if not siren or not name:
        return None
    updated: date | None = None
    try:
        updated = date.fromisoformat(str(record.get("date_mise_a_jour") or "")[:10])
    except ValueError:
        updated = None
    return RawListing(
        external_id=f"siren/{siren}",
        name=name[:200],
        source_name=source,
        source_url=f"https://annuaire-entreprises.data.gouv.fr/entreprise/{siren}",
        category=str(seat.get("activite_principale") or "") or None,
        address=str(seat.get("adresse") or "") or None,
        postcode=str(seat.get("code_postal") or "") or None,
        city=str(seat.get("libelle_commune") or "") or None,
        last_updated=updated,
        lat=_number(seat.get("latitude")),
        lon=_number(seat.get("longitude")),
        raw=cap_raw({"siren": siren, "activite_principale": seat.get("activite_principale"), "nom_complet": name}),
    )
