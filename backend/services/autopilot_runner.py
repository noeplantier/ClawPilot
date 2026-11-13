"""One run of the autopilot (rules: services/outreach_os/autopilot.py). Never sends.

In order, and only what the owner authorised: (1) when due, search the zone on the map again (Overpass, through the
persisted map job and its limits) and add the places that published a phone AND an e-mail with the attested import
(waiting for review); (2) approve the qualified prospects that wait for review, at most `max_approvals`, in the
owner's name, each decision in the audit log; (3) prepare the AI drafts of the prospects approved now, within the
credits. Sending stays the active mandate's job. Every run is written in the audit log with what it did and skipped.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.session import AsyncSessionLocal
from models import MapAddManyIn, MapPlaceIn
from repositories import account_repo, audit_repo, map_job_repo, prospect_repo
from routes import auto_selection, map_search
from services import draft_runner, feature_flags, map_job_runner
from services.outreach_os import autopilot as rules
from services.outreach_os import map_jobs

logger = logging.getLogger("outreachos.autopilot")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _owner(session: AsyncSession, account_id: uuid.UUID, s: rules.Settings) -> Optional[dict]:
    """The owner who authorised it, as the routes see a user; None when that person left or is no longer an owner."""
    if not s.by_user_id:
        return None
    user = await account_repo.get_user_by_id(session, s.by_user_id)
    if user is None or user.account_id != account_id or user.role != "owner":
        return None
    return {"id": str(user.id), "org_id": str(account_id), "role": user.role, "email": user.email}


async def _search_and_add(
    session_factory: async_sessionmaker[AsyncSession],
    account_id: uuid.UUID,
    owner: dict,
    zone: rules.Zone,
    fetcher: Optional[Callable[[str], dict[str, Any]]],
) -> dict[str, Any]:
    if not feature_flags.is_enabled("external_sources"):
        return {"search": "skipped", "why": "FEATURE_EXTERNAL_SOURCES est désactivé : pas de recherche sur la carte."}
    if not feature_flags.is_enabled("prospect_import"):
        return {"search": "skipped", "why": "FEATURE_PROSPECT_IMPORT est désactivé : rien ne peut être ajouté."}
    box = map_jobs.Bbox(zone.south, zone.west, zone.north, zone.east)
    async with session_factory() as session:
        job = await map_job_repo.create_job(session, account_id, uuid.UUID(owner["id"]), box, zone.category)
        await session.commit()
        job_id = job.id
    await map_job_runner.execute(job_id, session_factory=session_factory, fetcher=fetcher)
    async with session_factory() as session:
        job = await map_job_repo.get_job_any(session, job_id)
        if job is None or job.status != "succeeded":
            return {
                "search": "failed",
                "job_id": str(job_id),
                "why": (job.error if job else None) or "recherche échouée",
            }
        rows = await map_job_repo.list_results(session, account_id, job_id)
        reachable = [r for r in rows if r.phone and r.email]  # only what a person could reach: never a guess
        out: dict[str, Any] = {"search": "ok", "job_id": str(job_id), "found": len(rows), "reachable": len(reachable)}
        if reachable:
            places = [MapPlaceIn(**{k: getattr(r, k) for k in map_job_repo.PLACE_FIELDS}) for r in reachable[:200]]
            added = await map_search.add_places(
                MapAddManyIn(places=places, attestation=True, approve=False, check_website=False),
                user=owner,
                session=session,
            )
            out.update(created=added.created, already_known=added.already_known, suppressed=added.suppressed)
        await session.commit()
    return out


async def run(
    account_id: uuid.UUID,
    now: Optional[datetime] = None,
    *,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    fetcher: Optional[Callable[[str], dict[str, Any]]] = None,
    manual: bool = False,
) -> dict[str, Any]:
    now = now or utcnow()
    async with session_factory() as session:
        s = rules.settings_of(await account_repo.autopilot_of(session, account_id))
        owner = await _owner(session, account_id, s)
    if not s.enabled:
        return {"status": "off"}
    if owner is None:  # the authorisation does not outlive the owner who gave it
        async with session_factory() as session:
            await account_repo.set_autopilot(session, account_id, rules.to_row(rules.disable(s)))
            await audit_repo.log(
                session,
                account_id,
                action="autopilot.stopped",
                resource_type="account",
                resource_id=account_id,
                diff={"why": "owner_gone"},
            )
            await session.commit()
        return {"status": "stopped", "why": "owner_gone"}
    plan = rules.plan(s, now)
    out: dict[str, Any] = {"status": "ok", "manual": manual}
    if plan.search and s.zone is not None:
        try:
            out["discovery"] = await _search_and_add(session_factory, account_id, owner, s.zone, fetcher)
        except Exception as exc:  # noqa: BLE001 (a run always ends with what happened, never half-silent)
            logger.warning("autopilot search account_id=%s failed: %s", account_id, type(exc).__name__)
            out["discovery"] = {"search": "failed", "why": type(exc).__name__}
    approved_ids: list[str] = []
    if plan.approve:
        async with session_factory() as session:
            rows = await prospect_repo.list_positions(session, account_id, limit=plan.approve, review_status="pending")
            ids = [r["id"] for r in rows]
            if ids:
                decided = await auto_selection.review_batch(
                    auto_selection.BatchIn(lead_ids=ids, decision="approve", note="Pilote automatique"),
                    user=owner,
                    session=session,
                )
                out["approval"] = decided.model_dump()
                approved_ids = ids
            else:
                out["approval"] = {"approved": 0}
            await session.commit()
    if plan.drafts and approved_ids:
        out["drafts"] = await draft_runner.prepare(
            account_id, session_factory=session_factory, only=[uuid.UUID(i) for i in approved_ids]
        )
    async with session_factory() as session:
        searched = (out.get("discovery") or {}).get("search") == "ok"
        await account_repo.set_autopilot(session, account_id, rules.to_row(rules.ran(s, now, searched=searched)))
        await audit_repo.log(
            session,
            account_id,
            action="autopilot.run",
            resource_type="account",
            resource_id=account_id,
            diff=_jsonable(out),
        )
        await session.commit()
    return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


async def run_all(now: Optional[datetime] = None, **kw: Any) -> dict[str, int]:
    """The scheduled visit: every account whose autopilot is on. One failing account never stops the others."""
    factory = kw.get("session_factory", AsyncSessionLocal)
    async with factory() as session:
        ids = await account_repo.autopilot_accounts(session)
    counts = {"accounts": len(ids), "failed": 0}
    for account_id in ids:
        try:
            await run(account_id, now, **kw)
        except Exception as exc:  # noqa: BLE001
            counts["failed"] += 1
            logger.warning("autopilot account_id=%s failed: %s", account_id, type(exc).__name__)
    return counts
