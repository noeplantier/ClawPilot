"""CRM tasks (todo/reminders) — attached to a lead and/or a campaign, optionally
assigned to a user. Distinct from the Celery background jobs in `tasks/` —
these are human-facing to-dos, not async work units."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Task

ACTIVE = Task.deleted_at.is_(None)


async def create_task(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    title: str,
    lead_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    assigned_to_user_id: Optional[str] = None,
    due_at: Optional[datetime] = None,
) -> Task:
    task = Task(
        account_id=account_id,
        title=title,
        lead_id=uuid.UUID(lead_id) if lead_id else None,
        campaign_id=uuid.UUID(campaign_id) if campaign_id else None,
        assigned_to_user_id=uuid.UUID(assigned_to_user_id) if assigned_to_user_id else None,
        due_at=due_at,
    )
    session.add(task)
    await session.flush()
    return task


async def list_tasks(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    lead_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    status: Optional[str] = None,
) -> list[Task]:
    stmt = select(Task).where(Task.account_id == account_id, ACTIVE)
    if lead_id:
        stmt = stmt.where(Task.lead_id == uuid.UUID(lead_id))
    if campaign_id:
        stmt = stmt.where(Task.campaign_id == uuid.UUID(campaign_id))
    if status:
        stmt = stmt.where(Task.status == status)
    result = await session.execute(stmt.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc()))
    return list(result.scalars().all())


async def get_task(session: AsyncSession, account_id: uuid.UUID, task_id: str) -> Optional[Task]:
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        return None
    result = await session.execute(select(Task).where(Task.id == tid, Task.account_id == account_id, ACTIVE))
    return result.scalar_one_or_none()


async def update_task(session: AsyncSession, account_id: uuid.UUID, task_id: str, updates: dict) -> Optional[Task]:
    task = await get_task(session, account_id, task_id)
    if not task:
        return None
    if "assigned_to_user_id" in updates:
        assignee = updates.pop("assigned_to_user_id")
        task.assigned_to_user_id = uuid.UUID(assignee) if assignee else None
    for key, value in updates.items():
        setattr(task, key, value)
    await session.flush()
    return task


async def delete_task(session: AsyncSession, account_id: uuid.UUID, task_id: str) -> bool:
    task = await get_task(session, account_id, task_id)
    if not task:
        return False
    task.deleted_at = func.now()
    return True
