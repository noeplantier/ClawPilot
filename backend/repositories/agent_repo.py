"""Agent persistence. `tasks_completed`/`tasks_in_queue` become real counters
once Celery automation jobs land (Phase 2+); for now this ports the existing
CRUD + toggle behavior 1:1 (plan doc section 1.20)."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Agent

ACTIVE = Agent.deleted_at.is_(None)


async def list_agents(session: AsyncSession, account_id: uuid.UUID) -> list[Agent]:
    result = await session.execute(
        select(Agent).where(Agent.account_id == account_id, ACTIVE).order_by(Agent.created_at.asc())
    )
    return list(result.scalars().all())


async def create_agent(session: AsyncSession, account_id: uuid.UUID, name: str, role: str) -> Agent:
    agent = Agent(account_id=account_id, name=name, role=role)
    session.add(agent)
    await session.flush()
    return agent


async def get_agent(session: AsyncSession, account_id: uuid.UUID, agent_id: str) -> Optional[Agent]:
    try:
        aid = uuid.UUID(agent_id)
    except ValueError:
        return None
    result = await session.execute(select(Agent).where(Agent.id == aid, Agent.account_id == account_id, ACTIVE))
    return result.scalar_one_or_none()


async def toggle_agent(session: AsyncSession, account_id: uuid.UUID, agent_id: str) -> Optional[Agent]:
    agent = await get_agent(session, account_id, agent_id)
    if not agent:
        return None
    agent.status = "paused" if agent.status == "running" else "running"
    return agent


async def count_agents(session: AsyncSession, account_id: uuid.UUID, *, status: Optional[str] = None) -> int:
    from sqlalchemy import func

    stmt = select(func.count()).select_from(Agent).where(Agent.account_id == account_id, ACTIVE)
    if status:
        stmt = stmt.where(Agent.status == status)
    result = await session.execute(stmt)
    return result.scalar_one()


async def delete_agent(session: AsyncSession, account_id: uuid.UUID, agent_id: str) -> bool:
    from sqlalchemy import func

    agent = await get_agent(session, account_id, agent_id)
    if not agent:
        return False
    agent.deleted_at = func.now()
    return True
