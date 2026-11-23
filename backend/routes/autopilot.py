"""The autopilot of an organisation: read it, turn it on (an owner, with four acknowledgements), stop it, run it now.

Nothing here sends a message: a run searches, adds, approves and prepares drafts (services/autopilot_runner.py);
sending stays the active mandate's job, inside its caps and every gate of the sender.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user, require_roles
from repositories import account_repo, audit_repo
from services import autopilot_runner, feature_flags, mandate
from services.outreach_os import autopilot as rules

router = APIRouter(prefix="/autopilot", tags=["autopilot"])
owner_only = require_roles("owner")
decider = require_roles("owner", "admin")


class ZoneIn(BaseModel):
    south: float
    west: float
    north: float
    east: float
    category: str


class AutopilotIn(BaseModel):
    zone: Optional[ZoneIn] = None
    search_every_hours: int = Field(default=24, ge=rules.MIN_SEARCH_HOURS, le=24 * 30)
    max_approvals: int = Field(default=rules.DEFAULT_APPROVALS, ge=0, le=rules.MAX_APPROVALS)
    drafts: bool = True
    acknowledgements: List[str] = Field(default_factory=list)


def _refuse(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, "retry_at": None})


async def _view(session: AsyncSession, account_id: uuid.UUID) -> dict:
    s = rules.settings_of(await account_repo.autopilot_of(session, account_id))
    p = rules.plan(s, autopilot_runner.utcnow())
    return {
        **rules.to_row(s),
        "next_search_at": p.next_search_at.isoformat() if p.next_search_at else None,
        "acknowledgements": list(rules.ACKNOWLEDGEMENTS),
        "limits": {"min_search_hours": rules.MIN_SEARCH_HOURS, "max_approvals": rules.MAX_APPROVALS},
        "categories": list(rules.CATEGORIES),
        # What else a full automatic chain needs, read from the server (names of switches only, never a value).
        "requirements": {
            "external_sources": feature_flags.is_enabled("external_sources"),
            "prospect_import": feature_flags.is_enabled("prospect_import"),
            "automation_max": mandate.enabled(),
            "live_sending": feature_flags.is_enabled("live_sending"),
        },
    }


@router.get("")
async def read(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await _view(session, uuid.UUID(user["org_id"]))


@router.put("")
async def turn_on(
    payload: AutopilotIn, user: dict = Depends(owner_only), session: AsyncSession = Depends(get_db_session)
):
    account_id = uuid.UUID(user["org_id"])
    current = rules.settings_of(await account_repo.autopilot_of(session, account_id))
    try:
        s = rules.configure(
            current,
            zone=payload.zone.model_dump() if payload.zone else None,
            search_every_hours=payload.search_every_hours,
            max_approvals=payload.max_approvals,
            drafts=payload.drafts,
            acknowledgements=payload.acknowledgements,
            user_id=user["id"],
            now=autopilot_runner.utcnow(),
        )
    except rules.Invalid as exc:
        await audit_repo.log(
            session,
            account_id,
            action="autopilot.refused",
            resource_type="account",
            resource_id=account_id,
            actor_user_id=uuid.UUID(user["id"]),
            diff={"code": exc.code},
        )
        await session.commit()  # the refusal is written before answering (get_db_session rolls back on an error)
        raise _refuse(422, exc.code, exc.label)
    await account_repo.set_autopilot(session, account_id, rules.to_row(s))
    await audit_repo.log(
        session,
        account_id,
        action="autopilot.enabled",
        resource_type="account",
        resource_id=account_id,
        actor_user_id=uuid.UUID(user["id"]),
        diff={
            "zone": rules.to_row(s)["zone"],
            "max_approvals": s.max_approvals,
            "search_every_hours": s.search_every_hours,
            "drafts": s.drafts,
            "acknowledgements": list(rules.ACKNOWLEDGEMENTS),
        },
    )
    return await _view(session, account_id)


@router.post("/disable")
async def turn_off(user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)):
    """Anyone who may decide can stop it at once (only an owner can turn it on)."""
    account_id = uuid.UUID(user["org_id"])
    s = rules.settings_of(await account_repo.autopilot_of(session, account_id))
    await account_repo.set_autopilot(session, account_id, rules.to_row(rules.disable(s)))
    await audit_repo.log(
        session,
        account_id,
        action="autopilot.disabled",
        resource_type="account",
        resource_id=account_id,
        actor_user_id=uuid.UUID(user["id"]),
    )
    return await _view(session, account_id)


@router.post("/run")
async def run_now(user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)):
    """« Lancer maintenant »: one run on demand, with exactly what the owner authorised."""
    account_id = uuid.UUID(user["org_id"])
    s = rules.settings_of(await account_repo.autopilot_of(session, account_id))
    if not s.enabled:
        raise _refuse(409, "autopilot_off", "Le pilote automatique est désactivé : un propriétaire doit l'activer.")
    await session.commit()  # the runner works with its own sessions
    out = await autopilot_runner.run(account_id, manual=True)
    return {"run": autopilot_runner._jsonable(out), **(await _view(session, account_id))}
