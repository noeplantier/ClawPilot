"""Live map search as persisted jobs: real businesses published on OpenStreetMap inside the visible map area.

POST /map/search creates a job (stored in `map_search_jobs`) and answers at once; a background runner asks the source
(cache first, one polite request), de-duplicates and stages the places in `map_search_results`; the page polls
GET /map/search/{id} then reads GET /map/search/{id}/places. A failure is a stored, explained job state (never an
opaque 502); the browser may then feed the job itself (POST /map/search/{id}/ingest) as an explicit fallback.
Staged places are NOT prospects: importing the selection goes through the attested import (POST /api/prospect-imports),
so origin, legal basis, suppression list and audit apply. Needs FEATURE_EXTERNAL_SOURCES. 6 searches/min per org.
"""

from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user, require_roles
from models import (
    CityHeatOut,
    ImportIn,
    MapAddIn,
    MapAddOut,
    MapFallbackOut,
    MapJobOut,
    MapParseIn,
    MapPlaceOut,
    MapProspectOut,
    MapSearchIn,
    MapSearchOut,
)
from repositories import audit_repo, map_job_repo, prospect_repo, suppression_repo
from routes import prospect_imports
from routes.prospects import heat_out
from services import feature_flags, map_job_runner, overpass_svc
from services.outreach_os import cities, importer, map_jobs, osm
from services.outreach_os.dedupe import build_candidate
from services.outreach_os.normalize import normalize_domain, normalize_email, normalize_phone
from services.rate_limit import AttemptLimiter

router = APIRouter(prefix="/map", tags=["map"])
decider = require_roles("owner", "admin")
_limiter = AttemptLimiter(6, 60.0)
_ingest_limiter = AttemptLimiter(12, 60.0)
_add_limiter = AttemptLimiter(60, 60.0)
IMPORT_ORIGIN = "OpenStreetMap contributors (ODbL), read live through the Overpass API from the map of this application"
MAX_PARSED_ELEMENTS = 1000


@router.get("/prospects", response_model=list[MapProspectOut])
async def my_prospects(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    """The organisation's own prospects that have a position (imported from the map or from a file with lat/lon)."""
    return await prospect_repo.list_positions(session, uuid.UUID(user["org_id"]))


@router.get("/cities", response_model=list[CityHeatOut])
async def my_cities(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    """Where the organisation's leads are: hot / warm / cold counted per town, hottest towns first."""
    return cities.merge(await prospect_repo.city_heat_rows(session, uuid.UUID(user["org_id"])))


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


def _refuse(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, "retry_at": None})


@router.post("/places/add", response_model=MapAddOut)
async def add_place(payload: MapAddIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)):
    """One click on a map point: the business becomes a prospect, and (by default) joins the CRM.

    The same attested import as the bulk form (origin = the OpenStreetMap page of the place, legal basis, suppression
    list, audit), for ONE place; optionally the business's own homepage (and its contact page) is read for a public
    e-mail, with robots.txt respected. `approve` records the person's own decision to add it to the CRM, in the audit
    trail; without it the prospect waits in the review queue. Nothing is sent: contacting still needs an approved draft
    and the send rules.
    """
    account_id = uuid.UUID(user["org_id"])
    if not feature_flags.is_enabled("prospect_import"):
        raise _refuse(403, "feature_disabled", "Adding places needs FEATURE_PROSPECT_IMPORT (off by default)")
    if payload.check_website and not feature_flags.is_enabled("external_sources"):
        raise _refuse(409, "external_sources_disabled", "Reading the business's website needs FEATURE_EXTERNAL_SOURCES")
    if not payload.attestation:
        raise _refuse(
            422,
            "attestation_required",
            "Confirm that you may use these professional contact details for B2B prospecting",
        )
    key = str(account_id)
    wait = _add_limiter.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429, detail="Too many additions: wait a minute", headers={"Retry-After": str(wait)}
        )
    _add_limiter.record(key)

    place = payload.place
    row = {
        "name": place.name,
        "address": place.address,
        "postcode": place.postcode,
        "city": place.city,
        "phone": place.phone,
        "email": place.email,
        "website": place.website,
        "category": place.category,
        "external_id": place.external_id,
        "source_url": place.source_url,
        "lat": place.lat,
        "lon": place.lon,
    }
    content = json.dumps([{k: v for k, v in row.items() if v not in (None, "")}], ensure_ascii=False)
    imported = await prospect_imports.import_prospects(
        ImportIn(
            format="json",
            content=content,
            filename="map-place.json",
            origin=IMPORT_ORIGIN,
            legal_basis="legitimate_interest_b2b",
            country=payload.country,
            language="fr",
            vertical="local business",
            preview=False,
            attestation=True,
            check_websites=payload.check_website and bool(place.website),
        ),
        user,
        session,
    )
    parsed = importer.parse_import(content, "json", source_name="map-place", default_source_url="import://map-place")
    lead = None
    if parsed.listings:
        lead = await prospect_repo.find_by_keys(session, account_id, build_candidate(parsed.listings[0]).match_keys)
    if lead is None:
        if imported.suppressed:
            raise _refuse(409, "suppressed", "This business is on your suppression list: it was not added")
        raise _refuse(422, "place_unreadable", "This place could not be read: it was not added")

    if payload.approve and lead.review_status != "approved":
        if await suppression_repo.is_suppressed(
            session,
            account_id,
            email=normalize_email(lead.email),
            phone=normalize_phone(lead.phone),
            domain=normalize_domain(lead.website),
        ):
            raise _refuse(409, "suppressed", "This business is on your suppression list: it cannot join the CRM")
        previous = lead.review_status
        await prospect_repo.set_review(session, lead, status="approved", user_id=uuid.UUID(user["id"]))
        await audit_repo.log(
            session,
            account_id,
            action="prospect.approved",
            resource_type="prospect",
            resource_id=lead.id,
            actor_user_id=uuid.UUID(user["id"]),
            diff={"from": previous, "to": "approved", "has_note": False, "via": "map_quick_add"},
        )
    score_row = await prospect_repo.latest_score(session, lead.id)
    return MapAddOut(
        lead_id=str(lead.id),
        name=lead.full_name,
        created=imported.created > 0,
        review_status=lead.review_status,
        in_crm=lead.review_status == "approved",
        email=lead.email,
        phone=lead.phone,
        website=lead.website,
        email_found_on_site=bool(lead.email) and not (place.email or "").strip(),
        website_checked=imported.sites_checked > 0,
        heat=heat_out(lead, score_row.score if score_row else None),
    )
