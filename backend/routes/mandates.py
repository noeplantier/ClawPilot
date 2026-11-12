"""The bounded automatic mode "Automatisation max" (docs/automation-max.md).

OFF by default: the server flag FEATURE_AUTOMATION_MAX is off unless an operator turns it on, and nothing acts
without an ACTIVE mandate. Creating, pausing, revoking: owner/admin. Activating (the explicit authorisation) and
revalidating: owner. Revoking works whatever the flag says. Nothing here sends a message by itself.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user, require_roles
from models import MandateActivateIn, MandateCreateIn, MandateOut
from repositories import campaign_repo, mandate_repo
from services import imap_svc, inbox_health, mandate

router = APIRouter(prefix="/mandates", tags=["mandates"])
decider = require_roles("owner", "admin")
owner_only = require_roles("owner")


def _account(user: dict) -> uuid.UUID:
    return uuid.UUID(user["org_id"])


def _uid(user: dict) -> uuid.UUID:
    return uuid.UUID(user["id"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _refused(exc: mandate.MandateRefused, status: int = 409) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.label})


async def _get(session: AsyncSession, user: dict, mandate_id: str):  # type: ignore[no-untyped-def]
    try:
        key = uuid.UUID(mandate_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Mandate not found")
    found = await mandate_repo.get(session, _account(user), key)
    if found is None:
        raise HTTPException(status_code=404, detail="Mandate not found")
    return found


@router.get("", response_model=MandateOut)
async def overview(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    """Is the mode available on this server, what a mandate must say, and the mandates of the organisation."""
    return MandateOut(data=await mandate.overview(session, _account(user)))


@router.post("", response_model=MandateOut)
async def create(
    payload: MandateCreateIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    """Write a mandate down (a draft: nothing automatic happens). Unbounded or incoherent limits are refused."""
    campaign = await campaign_repo.get_campaign(session, _account(user), payload.campaign_id)
    if campaign is None or campaign.zone is None:
        raise HTTPException(status_code=404, detail="Journey not found")
    try:
        created = await mandate.create(
            session,
            _account(user),
            _uid(user),
            campaign,
            name=payload.name.strip(),
            daily_cap=payload.daily_cap,
            total_cap=payload.total_cap,
            days=payload.days,
            window=(payload.window_start_hour, payload.window_end_hour),
            min_delay_seconds=payload.min_delay_seconds,
            search_every_hours=payload.search_every_hours,
            ai_budget=payload.ai_budget,
            stop_rules=payload.stop_rules.model_dump(),
            now=_now(),
        )
    except mandate.MandateRefused as exc:
        raise _refused(exc)
    return MandateOut(data=mandate.view(created))


@router.get("/{mandate_id}", response_model=MandateOut)
async def detail(
    mandate_id: str, user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)
):
    found = await _get(session, user, mandate_id)
    return MandateOut(
        data={
            **mandate.view(found),
            "journal": [
                {"at": e.created_at, "action": e.action, "actor": e.actor_type, "detail": e.detail}
                for e in await mandate_repo.events(session, found.id, 50)
            ],
        }
    )


async def _replies_read() -> bool:
    return await asyncio.to_thread(inbox_health.reading_now, imap_svc.is_configured())


@router.post("/{mandate_id}/activate", response_model=MandateOut)
async def activate(
    mandate_id: str,
    payload: MandateActivateIn,
    user: dict = Depends(owner_only),
    session: AsyncSession = Depends(get_db_session),
):
    """THE explicit authorisation: the four acknowledgements, everything configured, the replies being read, the mode
    available on this server. The mandate is pinned to what is true now; the run acts only inside it."""
    found = await _get(session, user, mandate_id)
    scheduler: dict[str, Any] = {}
    try:
        done = await mandate.activate(
            session,
            found,
            _uid(user),
            acknowledgements=payload.acknowledgements,
            now=_now(),
            reply_collection_ok=await _replies_read(),
            scheduler=scheduler,
        )
    except mandate.MandateRefused as exc:
        # a refusal is recorded BEFORE the HTTP error: get_db_session rolls back on an exception
        await mandate_repo.log(
            session, found, "activation_refused", actor_user_id=_uid(user), detail={"code": exc.code}
        )
        await session.commit()
        raise _refused(exc, 403 if exc.code == "feature_disabled" else 409)
    return MandateOut(data=mandate.view(done))


@router.post("/{mandate_id}/suspend", response_model=MandateOut)
async def suspend(mandate_id: str, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)):
    """The pause: nothing leaves, the plan stays; activate again to resume."""
    found = await _get(session, user, mandate_id)
    try:
        return MandateOut(data=await mandate.suspend(session, found, _uid(user), now=_now()))
    except mandate.MandateRefused as exc:
        raise _refused(exc)


@router.post("/{mandate_id}/revoke", response_model=MandateOut)
async def revoke(mandate_id: str, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)):
    """Immediate and final, whatever the server flag says: planned messages are cancelled, approvals withdrawn."""
    found = await _get(session, user, mandate_id)
    try:
        return MandateOut(data=await mandate.revoke(session, found, _uid(user), now=_now()))
    except mandate.MandateRefused as exc:
        raise _refused(exc)


@router.post("/{mandate_id}/revalidate", response_model=MandateOut)
async def revalidate(
    mandate_id: str, user: dict = Depends(owner_only), session: AsyncSession = Depends(get_db_session)
):
    """After a substantial change: pin the mandate to what is true now (a person has looked), then activate again."""
    found = await _get(session, user, mandate_id)
    try:
        return MandateOut(data=mandate.view(await mandate.revalidate(session, found, _uid(user), now=_now())))
    except mandate.MandateRefused as exc:
        raise _refused(exc)


@router.get("/{mandate_id}/report", response_model=MandateOut)
async def report(
    mandate_id: str, user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)
):
    """The compact report: what it did, what is left of its limits, its journal."""
    return MandateOut(data=await mandate.report(session, await _get(session, user, mandate_id), _now()))
