"""Automatic selection: the server picks, among the prospects waiting for review, the ones its eligibility policy
qualifies (e-mail, phone, address and position on a fresh source, a recent fit score), hottest first, and a person
approves the selection in one click.

The selection is the server's (`prospect_repo.list_positions`, the same decision as the map and the campaigns); the
approval is the person's own, recorded one prospect at a time in the audit trail, with the suppression list checked for
each. Nothing is sent: contacting still needs an approved draft and every send rule.
"""

from __future__ import annotations

import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user, require_roles
from repositories import audit_repo, prospect_repo, suppression_repo
from services.outreach_os.normalize import normalize_domain, normalize_email, normalize_phone

router = APIRouter(prefix="/prospects/auto", tags=["prospects"])
decider = require_roles("owner", "admin")
MAX_BATCH = 500


class SelectionItem(BaseModel):
    id: str
    name: str
    city: Optional[str] = None
    priority: Literal["qualified", "hot"]
    priority_label: Optional[str] = None
    score: Optional[int] = None  # None = not scored, never 0
    heat: Optional[dict] = None
    signals: List[str] = Field(default_factory=list)
    has_website: bool = False


class SelectionOut(BaseModel):
    total: int  # how many qualified prospects wait for review (up to `limit`)
    hot: int
    items: List[SelectionItem]


class BatchIn(BaseModel):
    lead_ids: List[str] = Field(min_length=1, max_length=MAX_BATCH)
    decision: Literal["approve", "reject"]
    note: Optional[str] = Field(default=None, max_length=1000)


class BatchOut(BaseModel):
    approved: int
    rejected: int
    suppressed: int  # on the suppression list: not approved
    skipped: int  # not found, not a discovery prospect, or already decided


@router.get("/selection", response_model=SelectionOut)
async def selection(
    limit: int = Query(default=200, ge=1, le=MAX_BATCH),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await prospect_repo.list_positions(session, uuid.UUID(user["org_id"]), limit=limit, review_status="pending")
    items = [
        SelectionItem(
            id=r["id"],
            name=r["name"],
            city=r["city"],
            priority=r["priority"],
            priority_label=r["priority_label"],
            score=r["score"],
            heat=r["heat"],
            signals=r["signals"],
            has_website=r["has_website"],
        )
        for r in rows
    ]
    return SelectionOut(total=len(items), hot=sum(1 for i in items if i.priority == "hot"), items=items)


@router.post("/review", response_model=BatchOut)
async def review_batch(
    payload: BatchIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    account_id = uuid.UUID(user["org_id"])
    actor = uuid.UUID(user["id"])
    out = {"approved": 0, "rejected": 0, "suppressed": 0, "skipped": 0}
    new_status = "approved" if payload.decision == "approve" else "rejected"
    for lead_id in dict.fromkeys(payload.lead_ids):  # a repeated id is decided once
        try:
            uuid.UUID(lead_id)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Not a prospect id: {lead_id[:40]}")
        lead = await prospect_repo.get(session, account_id, lead_id)
        if lead is None or lead.review_status != "pending":  # only a pending prospect is decided here
            out["skipped"] += 1
            continue
        if new_status == "approved" and await suppression_repo.is_suppressed(
            session,
            account_id,
            email=normalize_email(lead.email),
            phone=normalize_phone(lead.phone),
            domain=normalize_domain(lead.website),
        ):
            out["suppressed"] += 1
            continue
        await prospect_repo.set_review(session, lead, status=new_status, user_id=actor, note=payload.note)
        await audit_repo.log(
            session,
            account_id,
            action=f"prospect.{new_status}",
            resource_type="prospect",
            resource_id=lead.id,
            actor_user_id=actor,
            diff={"from": "pending", "to": new_status, "has_note": bool(payload.note), "via": "auto_selection"},
        )
        out[new_status] += 1
    return BatchOut(**out)
