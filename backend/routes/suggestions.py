"""What to do next, computed from the organisation's own data on every request: where to prospect and who to contact."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user
from models import FocusOut
from repositories import focus_repo, prospect_repo
from services.outreach_os import cities

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.get("/focus", response_model=FocusOut)
async def focus(
    zones: int = Query(5, ge=1, le=20),
    leads: int = Query(8, ge=1, le=30),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> FocusOut:
    """The towns with the most hot leads that can be called and e-mailed, and the hottest such leads. Counted from the
    stored leads: nothing is estimated and nothing is suggested when nothing qualifies (the lists are then empty)."""
    account_id = uuid.UUID(user["org_id"])
    merged = cities.merge(await prospect_repo.city_heat_rows(session, account_id))
    return FocusOut(
        generated_at=datetime.now(timezone.utc),
        zones=cities.best_zones(merged, zones),
        leads=await focus_repo.best_leads(session, account_id, leads),
    )
