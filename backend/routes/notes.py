"""CRM notes routes — free-text notes attached to a lead and/or a campaign."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user
from models import Note, NoteCreate
from repositories import notes_repo

router = APIRouter(prefix="/notes", tags=["notes"])


def _to_schema(n) -> Note:
    return Note(
        id=str(n.id),
        org_id=str(n.account_id),
        lead_id=str(n.lead_id) if n.lead_id else None,
        campaign_id=str(n.campaign_id) if n.campaign_id else None,
        author_user_id=str(n.author_user_id),
        body=n.body,
        created_at=n.created_at,
    )


@router.get("", response_model=List[Note])
async def list_notes(
    lead_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await notes_repo.list_notes(session, uuid.UUID(user["org_id"]), lead_id=lead_id, campaign_id=campaign_id)
    return [_to_schema(n) for n in rows]


@router.post("", response_model=Note)
async def create_note(
    payload: NoteCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    note = await notes_repo.create_note(
        session,
        uuid.UUID(user["org_id"]),
        author_user_id=uuid.UUID(user["id"]),
        body=payload.body,
        lead_id=payload.lead_id,
        campaign_id=payload.campaign_id,
    )
    return _to_schema(note)


@router.delete("/{note_id}")
async def delete_note(
    note_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    ok = await notes_repo.delete_note(session, uuid.UUID(user["org_id"]), note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}
