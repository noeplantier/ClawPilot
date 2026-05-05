"""Leads / CRM routes."""
import csv
import io
import asyncio
import random
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from typing import List, Optional
from pydantic import BaseModel

from models import Lead, LeadCreate, LeadUpdate, Activity
from deps import db, get_current_user
from services import engagement

router = APIRouter(prefix="/leads", tags=["leads"])


async def _log(org_id: str, kind: str, title: str, meta: dict | None = None):
    act = Activity(org_id=org_id, kind=kind, title=title, meta=meta or {})
    d = act.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.activity.insert_one(d)


class BulkLeadsIn(BaseModel):
    leads: List[LeadCreate]


class BulkLeadsOut(BaseModel):
    created: int
    skipped: int
    errors: List[str]
    lead_ids: List[str]


class BulkStageIn(BaseModel):
    lead_ids: List[str]
    stage: str


class BulkDeleteIn(BaseModel):
    lead_ids: List[str]


class BulkTagIn(BaseModel):
    lead_ids: List[str]
    tags: List[str]
    mode: str = "add"  # add | replace


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


@router.post("/bulk", response_model=BulkLeadsOut)
async def bulk_create_leads(payload: BulkLeadsIn, user: dict = Depends(get_current_user)):
    """Bulk import — dedupes by email within org."""
    created = 0
    skipped = 0
    errors: List[str] = []
    lead_ids: List[str] = []

    # Preload existing emails for dedup
    existing_emails = set()
    if any(l.email for l in payload.leads):
        async for row in db.leads.find({"org_id": user["org_id"], "email": {"$ne": None}}, {"_id": 0, "email": 1}):
            if row.get("email"):
                existing_emails.add(row["email"].lower())

    docs = []
    for row in payload.leads:
        try:
            if row.email and row.email.lower() in existing_emails:
                skipped += 1
                continue
            lead = Lead(org_id=user["org_id"], **row.model_dump())
            d = lead.model_dump()
            d["created_at"] = d["created_at"].isoformat()
            docs.append(d)
            lead_ids.append(lead.id)
            if row.email:
                existing_emails.add(row.email.lower())
            created += 1
        except Exception as e:
            errors.append(f"{row.full_name}: {str(e)[:80]}")

    if docs:
        await db.leads.insert_many(docs)

    await _log(user["org_id"], "lead.bulk", f"Bulk import · +{created} leads ({skipped} duplicates skipped)")
    return BulkLeadsOut(created=created, skipped=skipped, errors=errors, lead_ids=lead_ids)


@router.post("/bulk-stage")
async def bulk_update_stage(payload: BulkStageIn, user: dict = Depends(get_current_user)):
    res = await db.leads.update_many(
        {"id": {"$in": payload.lead_ids}, "org_id": user["org_id"]},
        {"$set": {"stage": payload.stage}},
    )
    await _log(user["org_id"], "lead.bulk_stage", f"Bulk stage update → {payload.stage} · {res.modified_count} leads")
    return {"updated": res.modified_count}


@router.post("/bulk-delete")
async def bulk_delete_leads(payload: BulkDeleteIn, user: dict = Depends(get_current_user)):
    res = await db.leads.delete_many(
        {"id": {"$in": payload.lead_ids}, "org_id": user["org_id"]},
    )
    await _log(user["org_id"], "lead.bulk_delete", f"Bulk delete · {res.deleted_count} leads removed")
    return {"deleted": res.deleted_count}


@router.post("/bulk-tag")
async def bulk_tag_leads(payload: BulkTagIn, user: dict = Depends(get_current_user)):
    if payload.mode == "replace":
        res = await db.leads.update_many(
            {"id": {"$in": payload.lead_ids}, "org_id": user["org_id"]},
            {"$set": {"tags": payload.tags}},
        )
    else:
        res = await db.leads.update_many(
            {"id": {"$in": payload.lead_ids}, "org_id": user["org_id"]},
            {"$addToSet": {"tags": {"$each": payload.tags}}},
        )
    await _log(
        user["org_id"],
        "lead.bulk_tag",
        f"Bulk {payload.mode} tags {payload.tags} · {res.modified_count} leads",
    )
    return {"updated": res.modified_count}


@router.post("/upload-csv", response_model=BulkLeadsOut)
async def upload_csv(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Upload a CSV file. Expected columns (any subset, case-insensitive):
    full_name OR name, email, phone, company, title, country, language, tags (comma-split), source, notes
    """
    content = (await file.read()).decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file has no header row")

    lowered = {h.strip().lower(): h for h in reader.fieldnames}

    def pick(row: dict, *candidates) -> Optional[str]:
        for c in candidates:
            key = lowered.get(c)
            if key and row.get(key):
                return str(row[key]).strip()
        return None

    items: List[LeadCreate] = []
    errors: List[str] = []
    for i, row in enumerate(reader, start=2):
        try:
            name = pick(row, "full_name", "name")
            if not name:
                continue
            tag_raw = pick(row, "tags", "tag")
            tags = [t.strip() for t in tag_raw.split(",")] if tag_raw else []
            items.append(LeadCreate(
                full_name=name,
                email=pick(row, "email"),
                phone=pick(row, "phone", "mobile"),
                company=pick(row, "company", "organization"),
                title=pick(row, "title", "role"),
                country=pick(row, "country"),
                language=pick(row, "language", "lang") or "en",
                tags=tags,
                source=pick(row, "source") or "csv_upload",
                notes=pick(row, "notes"),
            ))
        except Exception as e:
            errors.append(f"row {i}: {str(e)[:100]}")

    # Reuse bulk logic
    result = await bulk_create_leads(BulkLeadsIn(leads=items), user=user)
    # Merge CSV-parse errors
    result.errors = errors + result.errors
    return result


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


# ============================================================
# DYNAMIC CONVERSION ENGINE
# ============================================================

class EngagementIn(BaseModel):
    event: str  # delivered | opened | clicked | replied | bounced | unsubscribed | spam
    channel: str = "email"
    campaign_id: Optional[str] = None


@router.post("/{lead_id}/engagement", response_model=Lead)
async def apply_engagement(lead_id: str, payload: EngagementIn, user: dict = Depends(get_current_user)):
    """Manually fire an engagement event on a lead — updates score, stage, activity, campaign counters.

    Useful as a manual override or for the conversion demo. The webhooks (SendGrid + Twilio)
    automatically call the same engine when real events arrive.
    """
    lead = await db.leads.find_one({"id": lead_id, "org_id": user["org_id"]}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    updated = await engagement.apply(
        db,
        lead_id,
        payload.event,
        channel=payload.channel,
        campaign_id=payload.campaign_id,
    )
    if not updated:
        raise HTTPException(status_code=400, detail=f"Unknown engagement event: {payload.event}")
    if payload.event in ("bounced", "unsubscribed", "spam"):
        await engagement.remove_from_active_campaigns(db, lead_id, user["org_id"])
    return updated


@router.post("/conversion-demo")
async def conversion_demo(user: dict = Depends(get_current_user)):
    """Pick 6 random leads and walk them through a realistic engagement funnel.

    Demonstrates the dynamic conversion engine end-to-end without needing real SendGrid/Twilio events.
    Sequences: 6 delivered → 5 opened → 3 clicked → 2 replied → 1 bounced.
    Returns timeline of events.
    """
    leads = await db.leads.find(
        {"org_id": user["org_id"], "suppressed": {"$ne": True}}, {"_id": 0, "id": 1, "full_name": 1, "stage": 1, "score": 1}
    ).limit(20).to_list(20)

    if len(leads) < 4:
        raise HTTPException(status_code=400, detail="Need at least 4 active leads")

    sample = random.sample(leads, min(6, len(leads)))
    timeline = []

    funnel_steps = [
        ("delivered", sample),                              # all 6
        ("opened",    sample[:5]),                          # 5
        ("clicked",   sample[:3]),                          # 3
        ("replied",   sample[:2]),                          # 2 → qualified
        ("bounced",   sample[5:6] if len(sample) >= 6 else []),  # 1 bounced
    ]

    for event, batch in funnel_steps:
        for lead in batch:
            updated = await engagement.apply(db, lead["id"], event, channel="email")
            if updated:
                timeline.append({
                    "lead": lead["full_name"],
                    "event": event,
                    "score": updated.get("score"),
                    "stage": updated.get("stage"),
                    "suppressed": updated.get("suppressed", False),
                })
        await asyncio.sleep(0.05)  # tiny pause for activity ordering

    await _log(user["org_id"], "conversion.demo", f"Conversion demo · {len(timeline)} events fired across {len(sample)} leads")
    return {
        "leads_touched": len(sample),
        "events_fired": len(timeline),
        "timeline": timeline,
    }
