"""Leads / CRM routes."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

from models import Lead, LeadCreate, LeadUpdate, Activity
from deps import db, get_current_user

router = APIRouter(prefix="/leads", tags=["leads"])


async def _log(org_id: str, kind: str, title: str, meta: dict | None = None):
    act = Activity(org_id=org_id, kind=kind, title=title, meta=meta or {})
    d = act.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.activity.insert_one(d)


@router.get("", response_model=List[Lead])
async def list_leads(
    user: dict = Depends(get_current_user),
    stage: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(500, le=1000),
):
    q = {"org_id": user["org_id"]}
    if stage:
        q["stage"] = stage
    if search:
        q["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"company": {"$regex": search, "$options": "i"}},
        ]
    cursor = db.leads.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


@router.post("", response_model=Lead)
async def create_lead(payload: LeadCreate, user: dict = Depends(get_current_user)):
    lead = Lead(org_id=user["org_id"], **payload.model_dump())
    d = lead.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.leads.insert_one(d)
    await _log(user["org_id"], "lead.created", f"New lead added — {lead.full_name}")
    return lead


@router.patch("/{lead_id}", response_model=Lead)
async def update_lead(lead_id: str, payload: LeadUpdate, user: dict = Depends(get_current_user)):
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = await db.leads.find_one_and_update(
        {"id": lead_id, "org_id": user["org_id"]},
        {"$set": upd},
        projection={"_id": 0},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Lead not found")
    if "stage" in upd:
        await _log(user["org_id"], "lead.stage", f"{res['full_name']} → {upd['stage']}")
    return res


@router.delete("/{lead_id}")
async def delete_lead(lead_id: str, user: dict = Depends(get_current_user)):
    res = await db.leads.delete_one({"id": lead_id, "org_id": user["org_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"ok": True}


@router.post("/enrich")
async def enrich_leads(user: dict = Depends(get_current_user)):
    """Simulated enrichment pass — bumps scores and adds tags."""
    import random
    count = 0
    async for doc in db.leads.find({"org_id": user["org_id"]}, {"_id": 0, "id": 1, "score": 1, "tags": 1}):
        new_score = min(100, (doc.get("score") or 50) + random.randint(3, 12))
        tags = list(set((doc.get("tags") or []) + ["enriched"]))
        await db.leads.update_one({"id": doc["id"]}, {"$set": {"score": new_score, "tags": tags}})
        count += 1
    await _log(user["org_id"], "lead.enriched", f"Enriched {count} leads via agent Nyx")
    return {"enriched": count}
