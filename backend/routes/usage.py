"""Credits and outreach models: what is left today and in the current session, and which model writes the AI drafts.

Read: anyone of the organisation. Change the model: an owner or an admin.
Nothing here calls a provider or costs anything.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user, require_roles
from repositories import audit_repo, usage_repo
from services import credit_gate
from services.outreach_os import credits

router = APIRouter(prefix="/usage", tags=["usage"])
decider = require_roles("owner", "admin")


class ModelIn(BaseModel):
    model: str = Field(min_length=1, max_length=32)


@router.get("/credits")
async def read_credits(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await credit_gate.state(session, uuid.UUID(user["org_id"]))


@router.put("/model")
async def choose_model(
    payload: ModelIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    if not credits.is_model(payload.model):
        raise HTTPException(
            status_code=422,
            detail={"code": "unknown_model", "message": f"Unknown model: {payload.model}", "retry_at": None},
        )
    account_id = uuid.UUID(user["org_id"])
    previous = await usage_repo.outreach_model(session, account_id)
    await usage_repo.set_outreach_model(session, account_id, payload.model)
    await audit_repo.log(
        session,
        account_id,
        action="settings.outreach_model",
        resource_type="account",
        resource_id=account_id,
        actor_user_id=uuid.UUID(user["id"]),
        diff={"from": previous, "to": payload.model},
    )
    return await credit_gate.state(session, account_id)
