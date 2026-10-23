"""Live map search as persisted jobs: real businesses published on OpenStreetMap inside the visible map area.

POST /map/search creates a job (stored in `map_search_jobs`) and answers at once; a background runner asks the source
(cache first, one polite request), de-duplicates and stages the places in `map_search_results`; the page polls
GET /map/search/{id} then reads GET /map/search/{id}/places. A failure is a stored, explained job state (never an
opaque 502); the browser may then feed the job itself (POST /map/search/{id}/ingest) as an explicit fallback.
Staged places are NOT prospects: importing the selection goes through the attested import (POST /api/prospect-imports),
so origin, legal basis, suppression list and audit apply. Needs FEATURE_EXTERNAL_SOURCES. 6 searches/min per org.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user, require_roles
from models import MapFallbackOut, MapJobOut, MapParseIn, MapPlaceOut, MapProspectOut, MapSearchIn, MapSearchOut
from repositories import map_job_repo, prospect_repo
from services import feature_flags, map_job_runner, overpass_svc
from services.outreach_os import map_jobs, osm
from services.rate_limit import AttemptLimiter

router = APIRouter(prefix="/map", tags=["map"])
decider = require_roles("owner", "admin")
_limiter = AttemptLimiter(6, 60.0)
_ingest_limiter = AttemptLimiter(12, 60.0)
MAX_PARSED_ELEMENTS = 1000


@router.get("/prospects", response_model=list[MapProspectOut])
async def my_prospects(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    """The organisation's own prospects that have a position (imported from the map or from a file with lat/lon)."""
    return await prospect_repo.list_positions(session, uuid.UUID(user["org_id"]))


@router.get("/categories")
async def categories(user: dict = Depends(decider)):
    return {"categories": sorted(osm.CATEGORIES), "attribution": osm.ATTRIBUTION}


def _need_flag() -> None:
    if not feature_flags.is_enabled("external_sources"):
        raise HTTPException(status_code=409, detail="Map search needs FEATURE_EXTERNAL_SOURCES (off by default)")


def _job_out(job) -> MapJobOut:  # type: ignore[no-untyped-def]
    fallback = None
    if (
        job.status == "failed"
        and (job.error_code or "").startswith("overpass_")
        and job.error_code != "overpass_too_large"
    ):
        box = map_job_runner.box_of(job)
        fallback = MapFallbackOut(
            query=map_job_runner.query_for(box, job.category), endpoints=list(overpass_svc.endpoints())
        )
    return MapJobOut(
        id=str(job.id),
        status=job.status,
        category=job.category,
        south=job.south,
        west=job.west,
        north=job.north,
        east=job.east,
        source=job.source,
        result_count=job.result_count,
        truncated=job.truncated,
        cache_hit=job.cache_hit,
        error_code=job.error_code,
        error=job.error,
        duration_ms=job.duration_ms,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        fallback=fallback,
    )


def _places_out(places: list[dict]) -> list[MapPlaceOut]:
    return [MapPlaceOut.model_validate({k: p.get(k) for k in map_job_repo.PLACE_FIELDS}) for p in places]


async def _own_job(session: AsyncSession, user: dict, job_id: str):  # type: ignore[no-untyped-def]
    try:
        key = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Search not found")
    job = await map_job_repo.get_job(session, uuid.UUID(user["org_id"]), key)
    if job is None:
        raise HTTPException(status_code=404, detail="Search not found")
    if await map_job_repo.fail_if_stale(session, job, map_job_runner.utcnow()):
        await session.commit()
    return job


@router.post("/search", response_model=MapJobOut, status_code=202)
async def create_search(
    payload: MapSearchIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    _need_flag()
    box = map_jobs.Bbox(payload.south, payload.west, payload.north, payload.east)
    try:
        map_job_runner.query_for(box, payload.category)  # validates the area (snapped) and the category
    except osm.BadArea as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    org = uuid.UUID(user["org_id"])
    key = str(org)
    wait = _limiter.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429, detail="Too many searches: wait a minute", headers={"Retry-After": str(wait)}
        )
    _limiter.record(key)
    now = map_job_runner.utcnow()
    await map_job_repo.purge_old(session, org, now)
    user_id = uuid.UUID(user["id"]) if user.get("id") else None
    job = await map_job_repo.create_job(session, org, user_id, box, payload.category)
    await session.commit()  # the runner reads the job from its own session: it must be visible before it starts
    map_job_runner.schedule_job(job.id)
    return _job_out(job)


@router.get("/search", response_model=list[MapJobOut])
async def recent_searches(
    limit: int = 10, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    jobs = await map_job_repo.list_jobs(session, uuid.UUID(user["org_id"]), max(1, min(limit, 30)))
    return [_job_out(j) for j in jobs]


@router.get("/search/{job_id}", response_model=MapJobOut)
async def search_status(job_id: str, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)):
    return _job_out(await _own_job(session, user, job_id))


@router.get("/search/{job_id}/places", response_model=MapSearchOut)
async def search_places(job_id: str, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)):
    job = await _own_job(session, user, job_id)
    if job.status != "succeeded":
        raise HTTPException(status_code=409, detail=f"Search is {job.status}: no places yet")
    rows = await map_job_repo.list_results(session, job.account_id, job.id)
    return MapSearchOut(
        attribution=osm.ATTRIBUTION,
        license_note=osm.LICENSE_NOTE,
        truncated=job.truncated,
        places=_places_out([{k: getattr(r, k) for k in map_job_repo.PLACE_FIELDS} for r in rows]),
    )


@router.post("/search/{job_id}/ingest", response_model=MapJobOut)
async def ingest_browser_answer(
    job_id: str, payload: MapParseIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    """Explicit fallback: the browser asked a public Overpass server itself after the server could not. The answer goes
    through the same parser and de-duplication as a server-side one and completes the failed job."""
    _need_flag()
    job = await _own_job(session, user, job_id)
    if job.status != "failed":
        raise HTTPException(status_code=409, detail=f"Search is {job.status}: only a failed search can be completed")
    key = "ingest:" + str(job.account_id)
    wait = _ingest_limiter.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429, detail="Too many searches: wait a minute", headers={"Retry-After": str(wait)}
        )
    _ingest_limiter.record(key)
    elements = payload.data.get("elements")
    if not isinstance(elements, list) or len(elements) > MAX_PARSED_ELEMENTS:
        raise HTTPException(status_code=422, detail="Not an Overpass answer, or too large: zoom in")
    places, truncated = map_job_runner.places_from({"elements": [e for e in elements if isinstance(e, dict)]})
    await map_job_runner.persist_success(
        session,
        job,
        places,
        truncated,
        source="overpass_browser",
        cache_hit=False,
        now=map_job_runner.utcnow(),
        started=time.monotonic(),
    )
    return _job_out(job)
