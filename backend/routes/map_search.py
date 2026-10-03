"""Live map search: real businesses published on OpenStreetMap inside the visible map area.

Nothing is stored here: the result is shown on the map; importing the selection goes through the normal, attested import
(POST /api/prospect-imports) so origin, legal basis, suppression list and audit apply as for any list.
Needs FEATURE_EXTERNAL_SOURCES. Per-organisation limit: 6 searches per minute.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException

from deps import require_roles
from models import MapPlaceOut, MapSearchIn, MapSearchOut
from services import feature_flags, overpass_svc
from services.outreach_os import osm
from services.rate_limit import AttemptLimiter

router = APIRouter(prefix="/map", tags=["map"])
decider = require_roles("owner", "admin")
_limiter = AttemptLimiter(6, 60.0)


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
