"""The journey "zone -> draft -> approval" (docs/campaign-journey.md).

Reading is open to any member; creating, editing the template, approving, revoking and pausing need owner/admin, like
every other sending action. Nothing here sends a message: an approval writes drafts and a plan, the scheduled task
(tasks/campaign_tasks.py) sends each message later, every gate checked again at that moment.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Campaign
from db.session import get_db_session
from deps import get_current_user, require_roles
from models import (
    JourneyApproveIn,
    JourneyCreateIn,
    JourneyListOut,
    JourneyOut,
    JourneyRevokeIn,
    JourneyTemplateIn,
)
from repositories import campaign_repo
from services import journey
from services.outreach_os import campaign_template

router = APIRouter(prefix="/journeys", tags=["journeys"])
decider = require_roles("owner", "admin")


def _account(user: dict) -> uuid.UUID:
    return uuid.UUID(user["org_id"])


def _uid(user: dict) -> uuid.UUID:
    return uuid.UUID(user["id"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _journey(session: AsyncSession, user: dict, journey_id: str) -> Campaign:
    campaign = await campaign_repo.get_campaign(session, _account(user), journey_id)
    if campaign is None or campaign.kind != "individual" or campaign.zone is None:
        raise HTTPException(status_code=404, detail="Journey not found")
    return campaign


async def _scheduler() -> dict[str, Any]:
    """Whether a worker and the Beat are seen (the plan is only sent while they run)."""
    try:
        from services import celery_health

        snap = await asyncio.wait_for(asyncio.to_thread(celery_health.snapshot), timeout=4)
    except Exception:  # noqa: BLE001 (an unreachable broker is an answer: "not seen", never an error page)
        return {"worker_ok": False, "beat_ok": False}
    return {"worker_ok": bool(snap["worker"]["ok"]), "beat_ok": bool(snap["beat"]["ok"])}


def _refused(exc: journey.JourneyRefused) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": exc.code, "message": exc.label})


@router.get("/readiness", response_model=JourneyOut)
async def readiness(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    """The one-time setup (offer, sender identity, provider) as a short checklist: what blocks, what only informs."""
    return JourneyOut(data=await journey.readiness(session, _account(user), await _scheduler()))


@router.get("", response_model=JourneyListOut)
async def list_journeys(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return JourneyListOut(items=await journey.journeys(session, _account(user)))


@router.post("", response_model=JourneyOut)
async def create_journey(
    payload: JourneyCreateIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    """Draw a zone: candidates are the validated, qualified prospects positioned inside it. A first template is
    pre-filled from the offer. Nothing is approved, planned or sent."""
    try:
        campaign, selection = await journey.create(
            session,
            _account(user),
            _uid(user),
            name=payload.name.strip(),
            zone=payload.zone.model_dump(),
            size=payload.size,
            now=_now(),
        )
    except journey.JourneyRefused as exc:
        raise _refused(exc)
    return JourneyOut(
        data={"id": str(campaign.id), "selected": len(selection.picked), "excluded": len(selection.excluded)}
    )


@router.get("/{journey_id}", response_model=JourneyOut)
async def get_journey(
    journey_id: str, user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)
):
    """The approval screen: zone and coverage, audience and exclusions, template and examples, volume, sender,
    schedule, setup and approval state, computed from the data as it is now."""
    campaign = await _journey(session, user, journey_id)
    try:
        return JourneyOut(data=await journey.summary(session, _account(user), campaign, _now(), await _scheduler()))
    except journey.JourneyRefused as exc:
        raise _refused(exc)


@router.put("/{journey_id}/template", response_model=JourneyOut)
async def put_template(
    journey_id: str,
    payload: JourneyTemplateIn,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Edit the message template. A change of wording is a new version and the earlier approval no longer covers it."""
    campaign = await _journey(session, user, journey_id)
    try:
        return JourneyOut(
            data=await journey.edit_template(
                session, _account(user), _uid(user), campaign, subject=payload.subject, body=payload.body
            )
        )
    except journey.JourneyRefused as exc:
        raise _refused(exc)


@router.post("/{journey_id}/approve", response_model=JourneyOut)
async def approve(
    journey_id: str,
    payload: JourneyApproveIn,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Approve the campaign as shown: this template version, this zone, this offer, this sender, this many messages.
    If any of it changed since the screen was read, nothing is written (409) and the screen must be read again."""
    campaign = await _journey(session, user, journey_id)
    try:
        result = await journey.approve(
            session,
            _account(user),
            _uid(user),
            campaign,
            expected_hash=payload.content_hash,
            expected_count=payload.expected_count,
            now=_now(),
            scheduler=await _scheduler(),
        )
    except journey.JourneyRefused as exc:
        raise _refused(exc)
    except journey.ViewChanged as changed:
        label = (
            campaign_template.reason_label("template_changed")
            if changed.code == "template_changed"
            else f"{changed.actual} message(s) peuvent partir maintenant, pas {payload.expected_count} : relisez."
        )
        raise HTTPException(status_code=409, detail={"code": changed.code, "message": label, "actual": changed.actual})
    return JourneyOut(data=result)


@router.post("/{journey_id}/revoke", response_model=JourneyOut)
async def revoke(
    journey_id: str,
    payload: JourneyRevokeIn,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Withdraw the approval: nothing that has not left will leave, and the campaign is paused."""
    campaign = await _journey(session, user, journey_id)
    try:
        return JourneyOut(
            data=await journey.revoke(session, _account(user), _uid(user), campaign, reason=payload.reason, now=_now())
        )
    except journey.JourneyRefused as exc:
        raise _refused(exc)


@router.post("/{journey_id}/pause", response_model=JourneyOut)
async def pause(journey_id: str, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)):
    campaign = await _journey(session, user, journey_id)
    return JourneyOut(data=await journey.pause(session, _account(user), _uid(user), campaign, paused=True))


@router.post("/{journey_id}/resume", response_model=JourneyOut)
async def resume(journey_id: str, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)):
    campaign = await _journey(session, user, journey_id)
    try:
        return JourneyOut(data=await journey.pause(session, _account(user), _uid(user), campaign, paused=False))
    except journey.JourneyRefused as exc:
        raise _refused(exc)


@router.get("/{journey_id}/progress", response_model=JourneyOut)
async def progress(
    journey_id: str, user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)
):
    """The compact follow-up: progression, what needs the person, replies, pause state."""
    campaign = await _journey(session, user, journey_id)
    return JourneyOut(data=await journey.progress(session, _account(user), campaign, _now()))
