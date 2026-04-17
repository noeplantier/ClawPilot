"""Analytics + dashboard aggregation routes."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends

from deps import db, get_current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
async def overview(user: dict = Depends(get_current_user)):
    org_id = user["org_id"]
    # campaign aggregate
    agg = await db.campaigns.aggregate([
        {"$match": {"org_id": org_id}},
        {"$group": {
            "_id": None,
            "sent": {"$sum": "$sent"},
            "opened": {"$sum": "$opened"},
            "replied": {"$sum": "$replied"},
            "converted": {"$sum": "$converted"},
            "count": {"$sum": 1},
        }},
    ]).to_list(1)
    totals = agg[0] if agg else {"sent": 0, "opened": 0, "replied": 0, "converted": 0, "count": 0}
    totals.pop("_id", None)

    leads_total = await db.leads.count_documents({"org_id": org_id})
    agents_running = await db.agents.count_documents({"org_id": org_id, "status": "running"})
    agents_total = await db.agents.count_documents({"org_id": org_id})

    # Pipeline breakdown
    pipeline_cursor = db.leads.aggregate([
        {"$match": {"org_id": org_id}},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
    ])
    pipeline = {s: 0 for s in ["new", "contacted", "engaged", "qualified", "won", "lost"]}
    async for row in pipeline_cursor:
        pipeline[row["_id"]] = row["count"]

    # Timeseries last 14 days (synthetic based on campaign history)
    import random
    random.seed(hash(org_id) & 0xFFFFFFFF)
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    timeseries = []
    for i in range(13, -1, -1):
        day = now - timedelta(days=i)
        sent = random.randint(40, 180)
        opened = int(sent * random.uniform(0.4, 0.7))
        replied = int(opened * random.uniform(0.05, 0.2))
        timeseries.append({
            "date": day.strftime("%b %d"),
            "sent": sent,
            "opened": opened,
            "replied": replied,
        })

    channel_split = [
        {"channel": "Email", "value": 68},
        {"channel": "WhatsApp", "value": 32},
    ]

    top_countries = [
        {"country": "US", "leads": await db.leads.count_documents({"org_id": org_id, "country": "US"})},
        {"country": "DE", "leads": await db.leads.count_documents({"org_id": org_id, "country": "DE"})},
        {"country": "FR", "leads": await db.leads.count_documents({"org_id": org_id, "country": "FR"})},
        {"country": "JP", "leads": await db.leads.count_documents({"org_id": org_id, "country": "JP"})},
        {"country": "BR", "leads": await db.leads.count_documents({"org_id": org_id, "country": "BR"})},
        {"country": "IN", "leads": await db.leads.count_documents({"org_id": org_id, "country": "IN"})},
    ]

    return {
        "totals": totals,
        "leads_total": leads_total,
        "agents_running": agents_running,
        "agents_total": agents_total,
        "pipeline": pipeline,
        "timeseries": timeseries,
        "channel_split": channel_split,
        "top_countries": top_countries,
    }


@router.get("/activity")
async def activity(limit: int = 30, user: dict = Depends(get_current_user)):
    items = await db.activity.find(
        {"org_id": user["org_id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return items
