"""Campaign routes."""
import random
from fastapi import APIRouter, Depends, HTTPException
from typing import List

from models import Campaign, CampaignCreate, CampaignUpdate, Activity, Message
from deps import db, get_current_user

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


async def _log(org_id: str, kind: str, title: str):
    act = Activity(org_id=org_id, kind=kind, title=title)
    d = act.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.activity.insert_one(d)


@router.get("", response_model=List[Campaign])
async def list_campaigns(user: dict = Depends(get_current_user)):
    return await db.campaigns.find({"org_id": user["org_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("", response_model=Campaign)
async def create_campaign(payload: CampaignCreate, user: dict = Depends(get_current_user)):
    c = Campaign(org_id=user["org_id"], **payload.model_dump())
    d = c.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.campaigns.insert_one(d)
    await _log(user["org_id"], "campaign.created", f"Campaign '{c.name}' created")
    return c


@router.get("/{campaign_id}", response_model=Campaign)
async def get_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    c = await db.campaigns.find_one({"id": campaign_id, "org_id": user["org_id"]}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    return c


@router.patch("/{campaign_id}", response_model=Campaign)
async def update_campaign(campaign_id: str, payload: CampaignUpdate, user: dict = Depends(get_current_user)):
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=400, detail="No fields")
    res = await db.campaigns.find_one_and_update(
        {"id": campaign_id, "org_id": user["org_id"]},
        {"$set": upd},
        projection={"_id": 0},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Not found")
    if "status" in upd:
        await _log(user["org_id"], f"campaign.{upd['status']}", f"{res['name']} → {upd['status']}")
    return res


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    r = await db.campaigns.delete_one({"id": campaign_id, "org_id": user["org_id"]})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@router.post("/{campaign_id}/launch")
async def launch_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    """Simulate dispatch: increment sent counters, write activity + message logs."""
    c = await db.campaigns.find_one({"id": campaign_id, "org_id": user["org_id"]}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Not found")

    leads_count = len(c.get("lead_ids") or []) or 50
    burst = min(leads_count, random.randint(20, 80))
    opened = int(burst * random.uniform(0.3, 0.6))
    replied = int(opened * random.uniform(0.05, 0.15))
    converted = max(0, int(replied * random.uniform(0.1, 0.35)))

    await db.campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"status": "running"}, "$inc": {"sent": burst, "opened": opened, "replied": replied, "converted": converted}},
    )
    await _log(user["org_id"], "campaign.launched", f"{c['name']} dispatched {burst} messages")
    return {"ok": True, "dispatched": burst, "opened": opened, "replied": replied, "converted": converted}
