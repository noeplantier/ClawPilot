"""Tag catalog routes — create/list/delete colored tags. Attaching/detaching a
tag to a specific lead lives on the leads router (POST/DELETE
/leads/{lead_id}/tags/{tag_id}) since that's the resource actually mutated.
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user
from models import Tag, TagCreate
from repositories import tags_repo

router = APIRouter(prefix="/tags", tags=["tags"])


def _to_schema(t) -> Tag:
    return Tag(id=str(t.id), org_id=str(t.account_id), name=t.name, color=t.color, created_at=t.created_at)


@router.get("", response_model=List[Tag])
async def list_tags(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await tags_repo.list_tags(session, uuid.UUID(user["org_id"]))
    return [_to_schema(t) for t in rows]


@router.post("", response_model=Tag)
async def create_tag(
    payload: TagCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account_id = uuid.UUID(user["org_id"])
    existing = await tags_repo.get_tag_by_name(session, account_id, payload.name)
    if existing:
        raise HTTPException(status_code=400, detail="A tag with this name already exists")
    tag = await tags_repo.create_tag(session, account_id, name=payload.name, color=payload.color)
    return _to_schema(tag)


@router.delete("/{tag_id}")
async def delete_tag(
    tag_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    ok = await tags_repo.delete_tag(session, uuid.UUID(user["org_id"]), tag_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}
