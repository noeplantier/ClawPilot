"""Discovery sources: one endpoint for every provider (OpenStreetMap, French company registry, world demo).

POST /api/sources/discover           run a discovery (rate limited per IP, per user, per organisation + provider;
  audited)
GET  /api/sources                    the providers, what they need, their limits and licence
GET  /api/sources/runs/{id}          page through a run's results (kept 30 minutes, in memory)
POST /api/sources/runs/{id}/add      add selected results to the prospects (attested; same pipeline, review queue,
  audit)

Nothing here sends anything. Network providers need FEATURE_EXTERNAL_SOURCES; adding real data needs
FEATURE_PROSPECT_IMPORT.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user, require_roles
from models import (
    AddFromRunIn,
    AddFromRunOut,
    DiscoveredPlace,
    DiscoveredSignal,
    DiscoverIn,
    DiscoverOut,
    SourceInfo,
)
from repositories import audit_repo
from services import discovery_runs, feature_flags, overpass_svc, registry_svc
from services.outreach_os import discovery, importer, osm, pipeline
from services.outreach_os import signals as sig
from services.outreach_os import source_adapters
from services.outreach_os.discovery import DiscoveryAdapter, SourceParams
from services.outreach_os.types import RawListing
from services.rate_limit import AttemptLimiter
from services.site_fetcher_svc import HttpSiteFetcher

router = APIRouter(prefix="/sources", tags=["sources"])
decider = require_roles("owner", "admin")

# Per client address, per user and per organisation+provider (the last one comes from the adapter's RateLimit).
_ip_limiter = AttemptLimiter(30, 60.0)
_user_limiter = AttemptLimiter(20, 60.0)
_provider_limiters: dict[str, AttemptLimiter] = {}
PAGE_MAX = 100


def adapters() -> dict[str, DiscoveryAdapter]:
    """The providers. Tests replace the HTTP callables on this module, never the network."""
    found: list[DiscoveryAdapter] = [
        discovery.WorldFixtureAdapter(),
        source_adapters.OsmAdapter(lambda query: overpass_svc.default_fetcher(query)),
        source_adapters.FrenchRegistryAdapter(lambda params: registry_svc.fetch_page(params)),
    ]
    return {a.name: a for a in found}


def _availability(adapter: DiscoveryAdapter) -> tuple[bool, str | None]:
    if adapter.kind == "network" and not feature_flags.is_enabled("external_sources"):
        return False, "FEATURE_EXTERNAL_SOURCES is off on this server"
    return True, None


def _info(adapter: DiscoveryAdapter) -> SourceInfo:
    ok, why = _availability(adapter)
    return SourceInfo(
        name=adapter.name,
        label=adapter.label,
        kind=adapter.kind,  # type: ignore[arg-type]
        available=ok,
        unavailable_reason=why,
        verticals=list(adapter.verticals),
        needs_position=adapter.kind == "network",
        max_radius_m=adapter.max_radius_m,
        rate_limit_per_minute=adapter.rate_limit.per_minute,
        rate_limit_note=adapter.rate_limit.note,
        license_note=adapter.license_note,
    )


def _place(listing: RawListing, adapter: DiscoveryAdapter, today: date) -> DiscoveredPlace:
    results = sig.analyze(listing, None, now=today, trust_absence=adapter.trust_absence)
    return DiscoveredPlace(
        external_id=listing.external_id,
        name=listing.name,
        category=listing.category,
        address=listing.address,
        postcode=listing.postcode,
        city=listing.city,
        phone=listing.phone,
        email=listing.email,
        website=listing.website,
        lat=listing.lat,
        lon=listing.lon,
        source_name=listing.source_name,
        source_url=listing.source_url,
        last_updated=listing.last_updated.isoformat() if listing.last_updated else None,
        signals=[DiscoveredSignal(key=r.key, state=r.state.value, evidence=r.evidence) for r in results],
    )


async def _deny(
    session: AsyncSession, user: dict, status: int, code: str, message: str, provider: str, retry: int | None = None
) -> HTTPException:
    """Record the refusal durably (the session rolls back on an HTTPException), then return the error to raise."""
    await audit_repo.log(
        session,
        uuid.UUID(user["org_id"]),
        action="sources.refused",
        resource_type="discovery_run",
        actor_user_id=uuid.UUID(user["id"]),
        diff={"code": code, "provider": provider},
    )
    await session.commit()
    headers = {"Retry-After": str(retry)} if retry else None
    return HTTPException(status_code=status, detail={"code": code, "message": message}, headers=headers)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("", response_model=list[SourceInfo])
async def list_sources(user: dict = Depends(get_current_user)):
    return [_info(a) for a in adapters().values()]


@router.post("/discover", response_model=DiscoverOut)
async def discover(
    payload: DiscoverIn,
    request: Request,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    account_id = uuid.UUID(user["org_id"])
    adapter = adapters().get(payload.provider)
    if adapter is None:
        raise HTTPException(status_code=422, detail={"code": "unknown_provider", "message": "Unknown provider"})
    ok, why = _availability(adapter)
    if not ok:
        raise await _deny(session, user, 409, "provider_disabled", why or "", adapter.name)

    org_limiter = _provider_limiters.setdefault(
        f"{account_id}:{adapter.name}", AttemptLimiter(adapter.rate_limit.per_minute, 60.0)
    )
    for label, limiter, key in (
        ("ip", _ip_limiter, _client_ip(request)),
        ("user", _user_limiter, user["id"]),
        ("provider", org_limiter, "x"),
    ):
        wait = limiter.retry_after(key)
        if wait:
            raise await _deny(
                session, user, 429, f"rate_limited_{label}", "Too many searches: wait", adapter.name, wait
            )
        limiter.record(key)

    params = SourceParams(
        vertical=payload.vertical,
        limit=payload.limit,
        country=payload.country,
        city=payload.city,
        lat=payload.lat,
        lon=payload.lon,
        radius_m=payload.radius_m,
    )
    try:
        discovery.check_params(adapter, params)
        if adapter.kind == "network" and not params.country:
            raise discovery.BadParams("country is required for this provider (it sets the language and send windows)")
        result = await asyncio.to_thread(adapter.fetch, params)
    except (discovery.BadParams, osm.BadArea) as exc:
        raise HTTPException(status_code=422, detail={"code": "bad_params", "message": str(exc)})
    except (overpass_svc.Unavailable, registry_svc.Unavailable) as exc:
        raise await _deny(session, user, 502, "provider_unavailable", str(exc), adapter.name)

    unique, merged = discovery.dedupe_listings(result.listings)
    ordered = discovery.sort_by_distance(unique, params)[: params.limit]
    run = discovery_runs.Run(
        id=uuid.uuid4(),
        account_id=account_id,
        provider=adapter.name,
        vertical=params.vertical,
        country=params.country,
        listings=ordered,
        duplicates_merged=merged,
        truncated=result.truncated,
    )
    discovery_runs.runs.put(run)
    await audit_repo.log(
        session,
        account_id,
        action="sources.discover",
        resource_type="discovery_run",
        resource_id=run.id,
        actor_user_id=uuid.UUID(user["id"]),
        diff={  # parameters and counts only: never the places themselves
            "provider": adapter.name,
            "vertical": params.vertical,
            "country": params.country,
            "city": params.city,
            "lat": params.lat,
            "lon": params.lon,
            "radius_m": params.radius_m,
            "limit": params.limit,
            "results": len(ordered),
            "duplicates_merged": merged,
            "raw_sha256": result.raw_sha256,
            "raw_bytes": result.raw_bytes,
            "licence": adapter.license_note,
        },
    )
    return _page(run, adapter, 0, min(params.limit, 25))


def _page(run: discovery_runs.Run, adapter: DiscoveryAdapter, offset: int, limit: int) -> DiscoverOut:
    today = date.today()
    chunk = run.listings[offset : offset + limit]
    return DiscoverOut(
        run_id=str(run.id),
        provider=run.provider,
        license_note=adapter.license_note,
        total=len(run.listings),
        duplicates_merged=run.duplicates_merged,
        truncated=run.truncated,
        offset=offset,
        limit=limit,
        places=[_place(item, adapter, today) for item in chunk],
    )


def _run_or_410(account_id: uuid.UUID, run_id: str) -> discovery_runs.Run:
    try:
        run = discovery_runs.runs.get(account_id, uuid.UUID(run_id))
    except ValueError:
        run = None
    if run is None:
        raise HTTPException(status_code=410, detail={"code": "run_expired", "message": "Results expired: search again"})
    return run


@router.get("/runs/{run_id}", response_model=DiscoverOut)
async def get_run(
    run_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=PAGE_MAX),
    user: dict = Depends(get_current_user),
):
    run = _run_or_410(uuid.UUID(user["org_id"]), run_id)
    return _page(run, adapters()[run.provider], offset, limit)


@router.post("/runs/{run_id}/add", response_model=AddFromRunOut)
async def add_from_run(
    run_id: str,
    payload: AddFromRunIn,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    account_id = uuid.UUID(user["org_id"])
    run = _run_or_410(account_id, run_id)
    adapter = adapters()[run.provider]
    if not payload.attestation:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "attestation_required",
                "message": "Confirm that you may use these details (legitimate interest)",
            },
        )
    if adapter.kind == "network" and not feature_flags.is_enabled("prospect_import"):
        raise await _deny(
            session, user, 403, "feature_disabled", "Adding real data needs FEATURE_PROSPECT_IMPORT", adapter.name
        )
    if payload.check_websites and not feature_flags.is_enabled("external_sources"):
        raise await _deny(
            session,
            user,
            409,
            "external_sources_disabled",
            "Checking websites needs FEATURE_EXTERNAL_SOURCES",
            adapter.name,
        )
    wanted = set(payload.external_ids)
    chosen = [item for item in run.listings if item.external_id in wanted]
    if len(chosen) != len(wanted):
        raise HTTPException(
            status_code=422, detail={"code": "unknown_selection", "message": "Some results are not in this run"}
        )

    groups: dict[str, list[RawListing]] = defaultdict(list)
    for item in chosen:  # the demo covers the world: each place keeps its own country
        country = (run.country or (item.raw or {}).get("country") or "FR").upper()
        groups[country].append(item)
    totals = {"created": 0, "updated": 0, "merged": 0, "suppressed": 0, "sites": 0}
    for country, items in groups.items():
        summary = await pipeline.run_discovery(
            session,
            account_id,
            adapter=importer.ListAdapter(adapter.name, adapter.license_note, items),
            fetcher=HttpSiteFetcher() if payload.check_websites else importer.NoNetworkFetcher(),
            now=date.today(),
            user_id=uuid.UUID(user["id"]),
            vertical=run.vertical,
            country=country,
            language="fr" if country == "FR" else "en",
            trust_absence=adapter.trust_absence,
        )
        totals["created"] += summary.prospects_created
        totals["updated"] += summary.prospects_updated
        totals["merged"] += summary.duplicates_merged
        totals["suppressed"] += summary.suppressed
        totals["sites"] += summary.sites_checked
    await audit_repo.log(
        session,
        account_id,
        action="sources.added",
        resource_type="discovery_run",
        resource_id=run.id,
        actor_user_id=uuid.UUID(user["id"]),
        diff={"provider": adapter.name, "selected": len(chosen), "check_websites": payload.check_websites, **totals},
    )
    return AddFromRunOut(
        created=totals["created"],
        updated=totals["updated"],
        duplicates_merged=totals["merged"],
        suppressed=totals["suppressed"],
        sites_checked=totals["sites"],
    )
