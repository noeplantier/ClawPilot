"""Agent orchestration routes — Postgres-backed (agents table)."""

import random
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import db, get_current_user
from models import Activity, Agent, AgentCreate
from repositories import agent_repo

router = APIRouter(prefix="/agents", tags=["agents"])


def _to_schema(a) -> Agent:
    return Agent(
        id=str(a.id),
        org_id=str(a.account_id),
        name=a.name,
        role=a.role,
        status=a.status,
        tasks_completed=a.tasks_completed,
        tasks_in_queue=a.tasks_in_queue,
        last_heartbeat=a.last_heartbeat,
        created_at=a.created_at,
    )


async def _log(org_id: str, kind: str, title: str):
    act = Activity(org_id=org_id, kind=kind, title=title)
    d = act.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.activity.insert_one(d)


@router.get("", response_model=List[Agent])
async def list_agents(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    agents = await agent_repo.list_agents(session, uuid.UUID(user["org_id"]))
    now = datetime.now(timezone.utc)
    out = [_to_schema(a) for a in agents]
    for a in out:  # simulated heartbeat drift for display — not persisted
        a.last_heartbeat = now
    return out


@router.post("", response_model=Agent)
async def create_agent(
    payload: AgentCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    a = await agent_repo.create_agent(session, uuid.UUID(user["org_id"]), payload.name, payload.role)
    await _log(user["org_id"], "agent.created", f"Agent {a.name} spawned")
    return _to_schema(a)


@router.post("/{agent_id}/toggle")
async def toggle_agent(
    agent_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    a = await agent_repo.toggle_agent(session, uuid.UUID(user["org_id"]), agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    await _log(user["org_id"], f"agent.{a.status}", f"Agent {a.name} → {a.status}")
    return {"ok": True, "status": a.status}


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    ok = await agent_repo.delete_agent(session, uuid.UUID(user["org_id"]), agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@router.get("/{agent_id}/logs")
async def agent_logs(
    agent_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Return simulated live logs for the agent."""
    a = await agent_repo.get_agent(session, uuid.UUID(user["org_id"]), agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Not found")

    samples = [
        f"[{a.name}] tick — resolving next task",
        "[queue] pulled job: enrich_lead(priya.shah@acme.io)",
        "[llm] gemini-3-flash generation 142ms",
        "[smtp] sendgrid accepted message id=<redacted>",
        "[http] GET /crm/pipeline 200 17ms",
        "[parse] extracted 12 contacts from page",
        "[retry] backoff 450ms on 429",
        "[done] task complete — score+7",
    ]
    return {"agent_id": agent_id, "lines": random.sample(samples, k=6)}
