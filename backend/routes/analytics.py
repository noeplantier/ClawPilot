"""Analytics + dashboard aggregation routes."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user
from repositories import activity_repo, agent_repo, campaign_repo, lead_repo, outreach_repo

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
async def overview(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    org_id = user["org_id"]
    account_id = uuid.UUID(org_id)
    # campaign aggregate (campaigns now live in Postgres — see repositories/campaign_repo.py)
    totals = await campaign_repo.aggregate_totals(session, account_id)

    leads_total = await lead_repo.count_leads(session, account_id)
    agents_running = await agent_repo.count_agents(session, account_id, status="running")
    agents_total = await agent_repo.count_agents(session, account_id)

    # Pipeline breakdown (leads now live in Postgres — see repositories/lead_repo.py)
    counts = await lead_repo.pipeline_breakdown(session, account_id)
    pipeline = {s: 0 for s in ["new", "contacted", "engaged", "qualified", "won", "lost"]}
    pipeline.update(counts)

    # Timeseries last 14 days — real counts from outreach_events (replaces the
    # legacy synthetic `random.seed(hash(org_id))` data).
    daily = await outreach_repo.daily_event_counts(session, account_id, days=14)
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    timeseries = []
    for i in range(13, -1, -1):
        day = now - timedelta(days=i)
        key = day.strftime("%Y-%m-%d")
        sent = daily.get((key, "sent"), 0)
        opened = daily.get((key, "opened"), 0) + daily.get((key, "clicked"), 0)
        replied = daily.get((key, "replied"), 0)
        timeseries.append(
            {
                "date": day.strftime("%b %d"),
                "sent": sent,
                "opened": opened,
                "replied": replied,
            }
        )

    channel_counts = await outreach_repo.channel_send_counts(session, account_id)
    email_count = channel_counts.get("email", 0)
    whatsapp_count = channel_counts.get("whatsapp", 0)
    channel_total = email_count + whatsapp_count
    if channel_total:
        email_pct = round(email_count / channel_total * 100)
        whatsapp_pct = 100 - email_pct
    else:
        email_pct = whatsapp_pct = 0
    channel_split = [
        {"channel": "Email", "value": email_pct},
        {"channel": "WhatsApp", "value": whatsapp_pct},
    ]

    top_countries = [
        {"country": country, "leads": count} for country, count in await lead_repo.top_countries(session, account_id)
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
async def activity(
    limit: int = 30, user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)
):
    return await activity_repo.list_recent(session, user["org_id"], limit)
