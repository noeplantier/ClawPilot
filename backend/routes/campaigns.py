"""Campaign routes — Postgres-backed (campaigns + campaign_steps + campaign_leads)."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user
from models import Campaign, CampaignCreate, CampaignRescoreOut, CampaignStep, CampaignUpdate
from repositories import activity_repo, audit_repo, campaign_repo, consent_repo, lead_repo, outreach_repo, prospect_repo
from routes._refusal import block_detail
from services import legacy_email, scheduler, send_gate
from services.rate_limit import AttemptLimiter
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
    not_attempted: int = 0  # leads not reached because a limit, the pause or the kill switch stopped the step
    blocked: Optional[dict] = None  # {code, message, retry_at} when the step was stopped
    total: int


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
    await activity_repo.record(session, user["org_id"], "campaign.created", f"Campaign '{c.name}' created")
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
        await activity_repo.record(session, user["org_id"], f"campaign.{upd['status']}", f"{c.name} → {upd['status']}")
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
    await activity_repo.record(
        session,
        user["org_id"],
        "campaign.assigned",
        f"{c.name} +{len(payload.lead_ids)} leads assigned ({len(c.leads)} total)",
    )
    return _to_schema(c)


async def _execute_step(session: AsyncSession, account_id: uuid.UUID, c, step, leads: list[dict]) -> dict:
    """Send one campaign step to the given leads, one by one, through the send gate (kill switch, pause, limits).

    Stops at the first refusal: the leads not reached are reported as `not_attempted` with the reason, nothing is queued
    silently and nothing is faked. Consent is checked per lead exactly as before.
    """
    sent = mocked = failed = skipped = not_attempted = 0
    blocked: Optional[send_gate.SendBlocked] = None

    for index, lead in enumerate(leads):
        channel = step.channel
        body = _render(step.body or "", lead)
        contact_id = uuid.UUID(lead["contact_id"]) if lead.get("contact_id") else None

        if channel == "email":
            if not lead.get("email") or not consent_repo.can_send("email", lead["email_consent"]):
                skipped += 1
                continue
        elif not lead.get("phone") or not consent_repo.can_send("whatsapp", lead["whatsapp_consent"]):
            skipped += 1
            continue

        try:
            await send_gate.check(session, account_id, channel)
        except send_gate.SendBlocked as exc:
            blocked = exc
            not_attempted = len(leads) - index
            await audit_repo.log(
                session,
                account_id,
                action="send.blocked_limits",
                resource_type="campaign",
                resource_id=c.id,
                diff={"code": exc.code, "channel": channel, "step": step.step_index, "not_attempted": not_attempted},
            )
            break

        if channel == "email":
            subj = _render(step.subject or "", lead)
            try:
                prepared = await legacy_email.prepare(
                    session,
                    account_id,
                    to_email=lead["email"],
                    body=body,
                    lead_id=lead["id"],
                    source=lead.get("source"),
                )
            except legacy_email.EmailNotCompliant:
                skipped += 1
                continue
            body = prepared.body
            result = send_email(lead["email"], subj, body, headers=prepared.headers)
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
            campaign_id=str(c.id),
            campaign_step_id=str(step.id),
            lead_id=lead["id"],
        )

        if result["status"] == "sent":
            sent += 1
        elif result["status"] == "mock":
            mocked += 1
        else:
            failed += 1

    return {
        "sent": sent,
        "mocked": mocked,
        "failed": failed,
        "skipped": skipped,
        "not_attempted": not_attempted,
        "blocked": block_detail(blocked) if blocked else None,
    }


async def _campaign_leads(session: AsyncSession, account_id: uuid.UUID, c) -> list[dict]:
    lead_ids = [str(cl.lead_id) for cl in c.leads]
    if not lead_ids:
        raise HTTPException(status_code=400, detail="No leads assigned to this campaign — assign leads first")
    return await lead_repo.get_leads_by_ids(session, account_id, lead_ids)


@router.post("/{campaign_id}/run-step/{step_index}", response_model=RunStepOut)
async def run_step(
    campaign_id: str,
    step_index: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Execute one campaign step against all assigned leads, under the send limits and the pause."""
    account_id = uuid.UUID(user["org_id"])
    c = await campaign_repo.get_campaign(session, account_id, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")

    steps = sorted(c.steps, key=lambda s: s.step_index)
    if step_index < 0 or step_index >= len(steps):
        raise HTTPException(status_code=400, detail=f"Step index {step_index} out of range (0..{len(steps)-1})")

    step = steps[step_index]
    leads = await _campaign_leads(session, account_id, c)
    outcome = await _execute_step(session, account_id, c, step, leads)

    dispatched = outcome["sent"] + outcome["mocked"]
    await campaign_repo.increment_counters(session, account_id, campaign_id, sent=dispatched, set_status="running")
    await activity_repo.record(
        session,
        user["org_id"],
        "campaign.step",
        f"{c.name} · step {step_index+1}/{len(steps)} · {dispatched} dispatched"
        + (f" · stopped: {outcome['blocked']['code']}" if outcome["blocked"] else ""),
    )
    return RunStepOut(dispatched=dispatched, total=len(leads), **outcome)


@router.post("/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Start the campaign: really execute its first step now, under the send limits and the pause.

    This used to invent sent/opened/replied/converted numbers with `random`. It now sends (or records a mock send when
    the provider is not configured) and the counters only ever reflect real attempts; opens, replies and conversions
    come from webhooks, never from here.
    """
    account_id = uuid.UUID(user["org_id"])
    c = await campaign_repo.get_campaign(session, account_id, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    steps = sorted(c.steps, key=lambda s: s.step_index)
    if not steps:
        raise HTTPException(status_code=400, detail="This campaign has no steps")

    leads = await _campaign_leads(session, account_id, c)
    outcome = await _execute_step(session, account_id, c, steps[0], leads)
    dispatched = outcome["sent"] + outcome["mocked"]
    await campaign_repo.increment_counters(session, account_id, campaign_id, sent=dispatched, set_status="running")
    await activity_repo.record(
        session,
        user["org_id"],
        "campaign.launched",
        f"{c.name} launched · {dispatched} dispatched"
        + (f" · stopped: {outcome['blocked']['code']}" if outcome["blocked"] else ""),
    )
    return {"ok": True, "dispatched": dispatched, "total": len(leads), **outcome}


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
    await activity_repo.record(
        session,
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
    await activity_repo.record(
        session, user["org_id"], "campaign.schedule_cancel", f"Cancelled {cancelled} pending jobs"
    )
    return {"cancelled": cancelled}


# ---------------------------------------------------------------- rescoring
RESCORE_MAX_LEADS = 500
_rescore_limiter = AttemptLimiter(3, 60.0)  # per organisation: a batch touches up to RESCORE_MAX_LEADS leads


@router.post("/{campaign_id}/rescore", response_model=CampaignRescoreOut)
async def rescore_campaign(
    campaign_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Recompute the score of every lead in the campaign: discovery prospects from their stored signals (reviewer
    dismissals applied) with the active configuration, CRM leads with the CRM score. No new observation is made, nothing
    is sent. At most 3 batches a minute per organisation and 500 leads per batch; audited."""
    account_id = uuid.UUID(user["org_id"])
    campaign = await campaign_repo.get_campaign(session, account_id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    wait = _rescore_limiter.retry_after(str(account_id))
    if wait:
        raise HTTPException(
            status_code=429, detail="Too many rescoring batches: wait a minute", headers={"Retry-After": str(wait)}
        )
    lead_ids = [str(cl.lead_id) for cl in campaign.leads]
    if len(lead_ids) > RESCORE_MAX_LEADS:
        raise HTTPException(
            status_code=422, detail=f"A campaign of more than {RESCORE_MAX_LEADS} leads cannot be rescored in one call"
        )
    _rescore_limiter.record(str(account_id))
    prospects = crm = skipped = 0
    for lead_id in lead_ids:
        lead = await lead_repo.get_lead(session, account_id, lead_id)
        if lead is None:
            skipped += 1
        elif lead.review_status is not None:
            await prospect_repo.rescore_lead(session, account_id, lead, uuid.UUID(user["id"]))
            prospects += 1
        else:
            await lead_repo.rescore_lead(session, account_id, lead, computed_by="manual")
            crm += 1
    await audit_repo.log(
        session,
        account_id,
        action="campaign.rescored",
        resource_type="campaign",
        resource_id=campaign.id,
        actor_user_id=uuid.UUID(user["id"]),
        diff={"total": len(lead_ids), "prospects": prospects, "crm": crm, "skipped": skipped},
    )
    return CampaignRescoreOut(
        total=len(lead_ids), prospects_rescored=prospects, crm_leads_rescored=crm, skipped=skipped
    )
