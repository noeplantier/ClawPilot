"""Campaign routes."""
import random
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from pydantic import BaseModel

from models import Campaign, CampaignCreate, CampaignUpdate, Activity, Message
from deps import db, get_current_user
from services.sendgrid_svc import send_email
from services.twilio_svc import send_whatsapp

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class AssignLeadsIn(BaseModel):
    lead_ids: List[str]


class RunStepOut(BaseModel):
    dispatched: int
    sent: int
    mocked: int
    failed: int
    skipped: int
    total: int


def _render(template: str, lead: dict) -> str:
    if not template:
        return ""
    first = (lead.get("full_name") or "").split(" ")[0] or "there"
    mapping = {
        "{{first_name}}": first,
        "{{full_name}}": lead.get("full_name") or "",
        "{{company}}": lead.get("company") or "",
        "{{title}}": lead.get("title") or "",
        "{{country}}": lead.get("country") or "",
    }
    out = template
    for k, v in mapping.items():
        out = out.replace(k, v)
    return out


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


@router.post("/{campaign_id}/assign-leads", response_model=Campaign)
async def assign_leads(campaign_id: str, payload: AssignLeadsIn, user: dict = Depends(get_current_user)):
    c = await db.campaigns.find_one({"id": campaign_id, "org_id": user["org_id"]}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Not found")

    # Validate lead ids belong to org
    valid = await db.leads.count_documents({"id": {"$in": payload.lead_ids}, "org_id": user["org_id"]})
    if valid != len(payload.lead_ids):
        raise HTTPException(status_code=400, detail="Some leads do not belong to your organization")

    updated = list(set((c.get("lead_ids") or []) + payload.lead_ids))
    res = await db.campaigns.find_one_and_update(
        {"id": campaign_id, "org_id": user["org_id"]},
        {"$set": {"lead_ids": updated}},
        projection={"_id": 0},
        return_document=True,
    )
    await _log(user["org_id"], "campaign.assigned", f"{c['name']} +{len(payload.lead_ids)} leads assigned ({len(updated)} total)")
    return res


@router.post("/{campaign_id}/run-step/{step_index}", response_model=RunStepOut)
async def run_step(campaign_id: str, step_index: int, user: dict = Depends(get_current_user)):
    """Execute one campaign step against all assigned leads."""
    c = await db.campaigns.find_one({"id": campaign_id, "org_id": user["org_id"]}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Not found")

    steps = c.get("steps") or []
    if step_index < 0 or step_index >= len(steps):
        raise HTTPException(status_code=400, detail=f"Step index {step_index} out of range (0..{len(steps)-1})")

    step = steps[step_index]
    lead_ids = c.get("lead_ids") or []
    if not lead_ids:
        raise HTTPException(status_code=400, detail="No leads assigned to this campaign — assign leads first")

    leads = await db.leads.find({"id": {"$in": lead_ids}, "org_id": user["org_id"]}, {"_id": 0}).to_list(len(lead_ids))

    sent = mocked = failed = skipped = 0
    docs = []

    for lead in leads:
        channel = step.get("channel", "email")
        body = _render(step.get("body") or "", lead)

        if channel == "email":
            if not lead.get("email"):
                skipped += 1
                continue
            subj = _render(step.get("subject") or "", lead)
            result = send_email(lead["email"], subj, body)
            to = lead["email"]
        else:
            if not lead.get("phone"):
                skipped += 1
                continue
            subj = None
            result = send_whatsapp(lead["phone"], body)
            to = lead["phone"]

        msg = Message(
            org_id=user["org_id"],
            campaign_id=campaign_id,
            lead_id=lead["id"],
            channel=channel,
            to=to,
            subject=subj,
            body=body,
            status=result["status"],
            provider_id=result.get("provider_id"),
            error=result.get("error"),
        )
        d = msg.model_dump()
        d["created_at"] = d["created_at"].isoformat()
        docs.append(d)

        if result["status"] == "sent":
            sent += 1
        elif result["status"] == "mock":
            mocked += 1
        else:
            failed += 1

    if docs:
        await db.messages.insert_many(docs)

    dispatched = sent + mocked
    await db.campaigns.update_one(
        {"id": campaign_id, "org_id": user["org_id"]},
        {"$set": {"status": "running"}, "$inc": {"sent": dispatched}},
    )
    await _log(user["org_id"], "campaign.step", f"{c['name']} · step {step_index+1}/{len(steps)} · {dispatched} dispatched")

    return RunStepOut(dispatched=dispatched, sent=sent, mocked=mocked, failed=failed, skipped=skipped, total=len(leads))


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
