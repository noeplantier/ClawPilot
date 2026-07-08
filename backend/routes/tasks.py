"""CRM tasks routes — todo/reminders attached to a lead and/or a campaign.

Distinct from the Celery background jobs under `tasks/` (this router is
mounted at /api/tasks, that package has no HTTP surface at all).
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user
from models import Task, TaskCreate, TaskUpdate
from repositories import tasks_repo

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _to_schema(t) -> Task:
    return Task(
        id=str(t.id),
        org_id=str(t.account_id),
        lead_id=str(t.lead_id) if t.lead_id else None,
        campaign_id=str(t.campaign_id) if t.campaign_id else None,
        assigned_to_user_id=str(t.assigned_to_user_id) if t.assigned_to_user_id else None,
        title=t.title,
        status=t.status,
        due_at=t.due_at,
        created_at=t.created_at,
    )


@router.get("", response_model=List[Task])
async def list_tasks(
    lead_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await tasks_repo.list_tasks(
        session, uuid.UUID(user["org_id"]), lead_id=lead_id, campaign_id=campaign_id, status=status
    )
    return [_to_schema(t) for t in rows]


@router.post("", response_model=Task)
async def create_task(
    payload: TaskCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    task = await tasks_repo.create_task(
        session,
        uuid.UUID(user["org_id"]),
        title=payload.title,
        lead_id=payload.lead_id,
        campaign_id=payload.campaign_id,
        assigned_to_user_id=payload.assigned_to_user_id,
        due_at=payload.due_at,
    )
    return _to_schema(task)


@router.patch("/{task_id}", response_model=Task)
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=400, detail="No fields")
    task = await tasks_repo.update_task(session, uuid.UUID(user["org_id"]), task_id, upd)
    if not task:
        raise HTTPException(status_code=404, detail="Not found")
    return _to_schema(task)


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    ok = await tasks_repo.delete_task(session, uuid.UUID(user["org_id"]), task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}
