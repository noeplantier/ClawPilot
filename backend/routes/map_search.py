"""Live map search: real businesses published on OpenStreetMap inside the visible map area.

Nothing is stored here: the result is shown on the map; importing the selection goes through the normal, attested import
(POST /api/prospect-imports) so origin, legal basis, suppression list and audit apply as for any list.
Needs FEATURE_EXTERNAL_SOURCES. Per-organisation limit: 6 searches per minute.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user, require_roles
from models import MapParseIn, MapPlaceOut, MapProspectOut, MapQueryOut, MapSearchIn, MapSearchOut
from repositories import prospect_repo
from services import feature_flags, overpass_svc
from services.outreach_os import osm
from services.rate_limit import AttemptLimiter

router = APIRouter(prefix="/map", tags=["map"])
decider = require_roles("owner", "admin")
_limiter = AttemptLimiter(6, 60.0)
_parse_limiter = AttemptLimiter(12, 60.0)
MAX_PARSED_ELEMENTS = 1000


@router.get("/prospects", response_model=list[MapProspectOut])
async def my_prospects(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    """The organisation's own prospects that have a position (imported from the map or from a file with lat/lon)."""
    return await prospect_repo.list_positions(session, uuid.UUID(user["org_id"]))


@router.get("/categories")
async def categories(user: dict = Depends(decider)):
    return {"categories": sorted(osm.CATEGORIES), "attribution": osm.ATTRIBUTION}


@router.post("/search", response_model=MapSearchOut)
async def search(payload: MapSearchIn, user: dict = Depends(decider)):
    if not feature_flags.is_enabled("external_sources"):
        raise HTTPException(status_code=409, detail="Map search needs FEATURE_EXTERNAL_SOURCES (off by default)")
    try:
        query = osm.build_query(payload.south, payload.west, payload.north, payload.east, payload.category)
    except osm.BadArea as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    key = str(uuid.UUID(user["org_id"]))
    wait = _limiter.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429, detail="Too many searches: wait a minute", headers={"Retry-After": str(wait)}
        )
    _limiter.record(key)
    try:
        data = await asyncio.to_thread(overpass_svc.default_fetcher, query)
    except overpass_svc.Unavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return _answer(data)


def _answer(data: dict) -> MapSearchOut:
    listings = osm.parse_elements(data)
    return MapSearchOut(
        attribution=osm.ATTRIBUTION,
        license_note=osm.LICENSE_NOTE,
        truncated=len(data.get("elements", [])) >= osm.MAX_RESULTS,
        places=[
            MapPlaceOut(
                external_id=item.external_id,
                name=item.name,
                category=item.category,
                lat=item.lat or 0.0,
                lon=item.lon or 0.0,
                address=item.address,
                postcode=item.postcode,
                city=item.city,
                phone=item.phone,
                email=item.email,
                website=item.website,
                source_url=item.source_url,
            )
            for item in listings
        ],
    )


def _need_flag() -> None:
    if not feature_flags.is_enabled("external_sources"):
        raise HTTPException(status_code=409, detail="Map search needs FEATURE_EXTERNAL_SOURCES (off by default)")


@router.post("/query", response_model=MapQueryOut)
async def query(payload: MapSearchIn, user: dict = Depends(decider)):
    """The Overpass query for an area, built and validated here. The browser may send it to a public Overpass
    server itself (the API host's address is often throttled or unreachable) and hand the answer to /map/parse."""
    _need_flag()
    try:
        text = osm.build_query(payload.south, payload.west, payload.north, payload.east, payload.category)
    except osm.BadArea as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    key = str(uuid.UUID(user["org_id"]))
    wait = _limiter.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429, detail="Too many searches: wait a minute", headers={"Retry-After": str(wait)}
        )
    _limiter.record(key)
    return MapQueryOut(query=text, endpoints=list(overpass_svc.ENDPOINTS))


@router.post("/parse", response_model=MapSearchOut)
async def parse(payload: MapParseIn, user: dict = Depends(decider)):
    """Turn an Overpass answer fetched by the browser into places: the same parser as a server-side search (only
    published fields, a nameless element is dropped, nothing completed). The answer is the caller's own data."""
    _need_flag()
    key = "parse:" + str(uuid.UUID(user["org_id"]))
    wait = _parse_limiter.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429, detail="Too many searches: wait a minute", headers={"Retry-After": str(wait)}
        )
    _parse_limiter.record(key)
    elements = payload.data.get("elements")
    if not isinstance(elements, list) or len(elements) > MAX_PARSED_ELEMENTS:
        raise HTTPException(status_code=422, detail="Not an Overpass answer, or too large: zoom in")
    return _answer({"elements": [e for e in elements if isinstance(e, dict)]})
