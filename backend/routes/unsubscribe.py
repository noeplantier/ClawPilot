"""Public unsubscribe endpoint linked from every draft. No login: the signed token is the credential.

Opting out is idempotent and always safe, so GET also acts (mail scanners that prefetch the link can only
cause an over-cautious opt-out, never an unwanted send). POST supports one-click clients (RFC 8058).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import JWT_SECRET
from repositories import audit_repo, prospect_repo
from services.outreach_os.unsubscribe import parse_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/unsubscribe", tags=["unsubscribe"])

_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Désinscription</title>"
    "<p>Vous êtes désinscrit(e). Vous ne recevrez plus de messages de notre part.</p>"
)


async def _opt_out(token: str, session: AsyncSession) -> HTMLResponse:
    parsed = parse_token(JWT_SECRET, token)
    if parsed is None:
        raise HTTPException(status_code=404, detail="Invalid unsubscribe link")
    account_id, lead_id = parsed
    lead = await prospect_repo.get_any(session, account_id, str(lead_id))
    if lead is not None:  # already erased or unknown: nothing left to suppress, still answer success
        added = await prospect_repo.opt_out(session, account_id, lead, source="unsubscribe_link")
        await audit_repo.log(
            session,
            account_id,
            action="prospect.opted_out",
            resource_type="prospect",
            resource_id=lead.id,
            actor_type="system",
            diff={"channel": "email", "newly_suppressed": added},
        )
    return HTMLResponse(_PAGE)


@router.get("/{token}", response_class=HTMLResponse)
async def unsubscribe_get(token: str, session: AsyncSession = Depends(get_db_session)):
    return await _opt_out(token, session)


@router.post("/{token}", response_class=HTMLResponse)
async def unsubscribe_post(token: str, session: AsyncSession = Depends(get_db_session)):
    return await _opt_out(token, session)
