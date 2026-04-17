"""Agent (OpenClaw) orchestration routes."""
import random
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from typing import List

from models import Agent, AgentCreate, Activity
from deps import db, get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


async def _log(org_id: str, kind: str, title: str):
    act = Activity(org_id=org_id, kind=kind, title=title)
    d = act.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.activity.insert_one(d)


@router.get("", response_model=List[Agent])
async def list_agents(user: dict = Depends(get_current_user)):
    agents = await db.agents.find({"org_id": user["org_id"]}, {"_id": 0}).sort("created_at", 1).to_list(100)
    # Simulate heartbeat drift
    for a in agents:
        a["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
    return agents


@router.post("", response_model=Agent)
async def create_agent(payload: AgentCreate, user: dict = Depends(get_current_user)):
    a = Agent(org_id=user["org_id"], **payload.model_dump())
    d = a.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    d["last_heartbeat"] = d["last_heartbeat"].isoformat()
    await db.agents.insert_one(d)
    await _log(user["org_id"], "agent.created", f"Agent {a.name} spawned")
    return a


@router.post("/{agent_id}/toggle")
async def toggle_agent(agent_id: str, user: dict = Depends(get_current_user)):
    a = await db.agents.find_one({"id": agent_id, "org_id": user["org_id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    new_status = "paused" if a["status"] == "running" else "running"
    await db.agents.update_one({"id": agent_id}, {"$set": {"status": new_status}})
    await _log(user["org_id"], f"agent.{new_status}", f"Agent {a['name']} → {new_status}")
    return {"ok": True, "status": new_status}


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, user: dict = Depends(get_current_user)):
    r = await db.agents.delete_one({"id": agent_id, "org_id": user["org_id"]})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@router.get("/{agent_id}/logs")
async def agent_logs(agent_id: str, user: dict = Depends(get_current_user)):
    """Return simulated live logs for the agent."""
    a = await db.agents.find_one({"id": agent_id, "org_id": user["org_id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Not found")

    samples = [
        f"[{a['name']}] tick — resolving next task",
        "[queue] pulled job: enrich_lead(priya.shah@acme.io)",
        "[llm] gemini-3-flash generation 142ms",
        "[smtp] sendgrid accepted message id=<redacted>",
        "[http] GET /crm/pipeline 200 17ms",
        "[parse] extracted 12 contacts from page",
        "[retry] backoff 450ms on 429",
        "[done] task complete — score+7",
    ]
    return {"agent_id": agent_id, "lines": random.sample(samples, k=6)}
