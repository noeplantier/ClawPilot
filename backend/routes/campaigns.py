"""Campaign routes — Postgres-backed (campaigns + campaign_steps + campaign_leads)."""

import random
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import db, get_current_user
from models import Activity, Campaign, CampaignCreate, CampaignStep, CampaignUpdate
from repositories import campaign_repo, consent_repo, lead_repo, outreach_repo
from services import scheduler
from services.sendgrid_svc import send_email
from services.templating import render as _render
from services.twilio_svc import send_whatsapp

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _to_schema(c) -> Campaign:
    return Campaign(
        id=str(c.id),
        org_id=str(c.account_id),
        name=c.name,
        goal=c.goal,
        status=c.status,
        channels=list(c.channels),
        steps=[
            CampaignStep(
                id=str(s.id),
                channel=s.channel,
                delay_hours=s.delay_hours,
                subject=s.subject,
                body=s.body,
                language=s.language,
            )
            for s in sorted(c.steps, key=lambda s: s.step_index)
        ],
        lead_ids=[str(cl.lead_id) for cl in c.leads],
        agent_id=str(c.agent_id) if c.agent_id else None,
        sent=c.sent,
        opened=c.opened,
        replied=c.replied,
        converted=c.converted,
        created_at=c.created_at,
    )


class AssignLeadsIn(BaseModel):
    lead_ids: List[str]


class RunStepOut(BaseModel):
    dispatched: int
    sent: int
    mocked: int
    failed: int
    skipped: int
    total: int


async def _log(org_id: str, kind: str, title: str):
    act = Activity(org_id=org_id, kind=kind, title=title)
    d = act.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.activity.insert_one(d)


@router.get("", response_model=List[Campaign])
async def list_campaigns(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    rows = await campaign_repo.list_campaigns(session, uuid.UUID(user["org_id"]))
    return [_to_schema(c) for c in rows]


@router.post("", response_model=Campaign)
async def create_campaign(
    payload: CampaignCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    c = await campaign_repo.create_campaign(session, uuid.UUID(user["org_id"]), payload.model_dump())
    await _log(user["org_id"], "campaign.created", f"Campaign '{c.name}' created")
    return _to_schema(c)


@router.get("/{campaign_id}", response_model=Campaign)
async def get_campaign(
    campaign_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    c = await campaign_repo.get_campaign(session, uuid.UUID(user["org_id"]), campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    return _to_schema(c)


@router.patch("/{campaign_id}", response_model=Campaign)
async def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=400, detail="No fields")
    if "steps" in upd:
        upd["steps"] = [s if isinstance(s, dict) else s for s in upd["steps"]]
    c = await campaign_repo.update_campaign(session, uuid.UUID(user["org_id"]), campaign_id, upd)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    if "status" in upd:
        await _log(user["org_id"], f"campaign.{upd['status']}", f"{c.name} → {upd['status']}")
    return _to_schema(c)


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    ok = await campaign_repo.delete_campaign(session, uuid.UUID(user["org_id"]), campaign_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@router.post("/{campaign_id}/assign-leads", response_model=Campaign)
async def assign_leads(
    campaign_id: str,
    payload: AssignLeadsIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account_id = uuid.UUID(user["org_id"])
    existing = await campaign_repo.get_campaign(session, account_id, campaign_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")

    # Validate lead ids belong to org (leads live in Postgres — see repositories/lead_repo.py)
    found = await lead_repo.get_leads_by_ids(session, account_id, payload.lead_ids)
    if len(found) != len(payload.lead_ids):
        raise HTTPException(status_code=400, detail="Some leads do not belong to your organization")

    c = await campaign_repo.assign_leads(session, account_id, campaign_id, payload.lead_ids)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    await _log(
        user["org_id"],
        "campaign.assigned",
        f"{c.name} +{len(payload.lead_ids)} leads assigned ({len(c.leads)} total)",
    )
    return _to_schema(c)


@router.post("/{campaign_id}/run-step/{step_index}", response_model=RunStepOut)
async def run_step(
    campaign_id: str,
    step_index: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Execute one campaign step against all assigned leads."""
    account_id = uuid.UUID(user["org_id"])
    c = await campaign_repo.get_campaign(session, account_id, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")

    steps = sorted(c.steps, key=lambda s: s.step_index)
    if step_index < 0 or step_index >= len(steps):
        raise HTTPException(status_code=400, detail=f"Step index {step_index} out of range (0..{len(steps)-1})")

    step = steps[step_index]
    lead_ids = [str(cl.lead_id) for cl in c.leads]
    if not lead_ids:
        raise HTTPException(status_code=400, detail="No leads assigned to this campaign — assign leads first")

    leads = await lead_repo.get_leads_by_ids(session, account_id, lead_ids)

    sent = mocked = failed = skipped = 0

    for lead in leads:
        channel = step.channel
        body = _render(step.body or "", lead)
        contact_id = uuid.UUID(lead["contact_id"]) if lead.get("contact_id") else None

        if channel == "email":
            if not lead.get("email") or not consent_repo.can_send("email", lead["email_consent"]):
                skipped += 1
                continue
            subj = _render(step.subject or "", lead)
            result = send_email(lead["email"], subj, body)
            await outreach_repo.create_email_send(
                session,
                account_id,
                campaign_id=c.id,
                campaign_step_id=step.id,
                contact_id=contact_id,
                to_email=lead["email"],
                subject=subj,
                body=body,
                status=result["status"],
                provider_message_id=result.get("provider_id"),
                error=result.get("error"),
            )
        else:
            if not lead.get("phone") or not consent_repo.can_send("whatsapp", lead["whatsapp_consent"]):
                skipped += 1
                continue
            result = send_whatsapp(lead["phone"], body)
            await outreach_repo.create_whatsapp_send(
                session,
                account_id,
                campaign_id=c.id,
                contact_id=contact_id,
                direction="outbound",
                from_number="",
                to_number=lead["phone"],
                body=body,
                status=result["status"],
                provider_message_sid=result.get("provider_id"),
                error=result.get("error"),
            )

        await outreach_repo.record_outreach_event(
            session,
            account_id,
            channel=channel,
            event_type="failed" if result["status"] == "failed" else "sent",
            campaign_id=campaign_id,
            campaign_step_id=str(step.id),
            lead_id=lead["id"],
        )

        if result["status"] == "sent":
            sent += 1
        elif result["status"] == "mock":
            mocked += 1
        else:
            failed += 1

    dispatched = sent + mocked
    await campaign_repo.increment_counters(session, account_id, campaign_id, sent=dispatched, set_status="running")
    await _log(
        user["org_id"], "campaign.step", f"{c.name} · step {step_index+1}/{len(steps)} · {dispatched} dispatched"
    )

    return RunStepOut(dispatched=dispatched, sent=sent, mocked=mocked, failed=failed, skipped=skipped, total=len(leads))


@router.post("/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Simulate dispatch: increment sent counters, write activity + message logs."""
    account_id = uuid.UUID(user["org_id"])
    c = await campaign_repo.get_campaign(session, account_id, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")

    leads_count = len(c.leads) or 50
    burst = min(leads_count, random.randint(20, 80))
    opened = int(burst * random.uniform(0.3, 0.6))
    replied = int(opened * random.uniform(0.05, 0.15))
    converted = max(0, int(replied * random.uniform(0.1, 0.35)))

    await campaign_repo.increment_counters(
        session,
        account_id,
        campaign_id,
        sent=burst,
        opened=opened,
        replied=replied,
        converted=converted,
        set_status="running",
    )
    await _log(user["org_id"], "campaign.launched", f"{c.name} dispatched {burst} messages")
    return {"ok": True, "dispatched": burst, "opened": opened, "replied": replied, "converted": converted}


@router.post("/{campaign_id}/schedule")
async def schedule_campaign(
    campaign_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Enqueue every step × every assigned lead with cumulative delay_hours."""
    res = await scheduler.enqueue_campaign(session, campaign_id, user["org_id"])
    if res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])
    await campaign_repo.increment_counters(session, uuid.UUID(user["org_id"]), campaign_id, set_status="running")
    await _log(
        user["org_id"],
        "campaign.scheduled",
        f"Scheduled {res['scheduled']} jobs ({res['steps']} steps × {res['leads']} leads)",
    )
    return res


@router.get("/{campaign_id}/schedule")
async def list_schedule(
    campaign_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    jobs, counts = await scheduler.pending_for_campaign(session, campaign_id, user["org_id"])
    return {"jobs": jobs[:100], "counts": counts, "total": len(jobs)}


@router.post("/{campaign_id}/cancel-schedule")
async def cancel_schedule(
    campaign_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    cancelled = await scheduler.cancel_campaign(session, campaign_id, user["org_id"])
    await _log(user["org_id"], "campaign.schedule_cancel", f"Cancelled {cancelled} pending jobs")
    return {"cancelled": cancelled}
