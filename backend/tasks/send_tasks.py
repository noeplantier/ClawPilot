"""Celery send tasks — the distributed replacement for services/scheduler.py's
in-process poll loop. Same semantics (pause-aware, template rendering, consent
gate) plus what the asyncio version couldn't do: per-channel throttling and
timezone-aware send windows via `rate_limit` + a window check that re-schedules
itself with `self.retry(eta=...)` instead of executing early.

Pause/window retries pass `max_retries=None`: they're not errors, they're
"come back later", and could legitimately need to fire many more times than
the 5-retry budget meant for real transient failures (e.g. a lead in a narrow
timezone window skipped over a weekend).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from celery_app import celery_app
from repositories import campaign_repo, consent_repo, lead_repo, outreach_repo, send_policy_repo
from services import legacy_email, send_gate
from services.sendgrid_svc import send_email
from services.templating import render as _render
from services.timezones import resolve_timezone
from tasks._bridge import run_async

HALT_RETRY_SECONDS = 900  # kill switch / pause: look again in 15 minutes


def _retry_args(blocked: send_gate.SendBlocked) -> dict:
    """How a refused send is rescheduled: at the time the limit frees up, or later for a halt. Never a failure."""
    if blocked.retry_at is not None:
        return {"eta": blocked.retry_at.astimezone(timezone.utc).replace(tzinfo=None), "max_retries": None}
    return {"countdown": HALT_RETRY_SECONDS, "max_retries": None}


def _next_window_start(now_local: datetime, window_start_hour: int) -> datetime:
    candidate = now_local.replace(hour=window_start_hour, minute=0, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate


async def _check_window_or_get_eta(session, account_id: uuid.UUID, channel: str, country: str | None):
    """Returns None if sending now is fine, or a UTC datetime to retry at if
    we're outside the account's configured send window for this channel."""
    import zoneinfo

    policy = await send_policy_repo.get_policy(session, account_id, channel)
    tz_name = (
        resolve_timezone(country, default=policy.account_default_timezone)
        if policy.timezone_source == "lead_country"
        else policy.account_default_timezone
    )
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")

    now_local = datetime.now(tz)
    if send_policy_repo.in_window(policy, now_local.hour):
        return None
    next_start_local = _next_window_start(now_local, policy.window_start_hour)
    return next_start_local.astimezone(zoneinfo.ZoneInfo("UTC")).replace(tzinfo=None)


async def _send_email_impl(
    session, task, account_id: uuid.UUID, campaign_id: str, campaign_step_id: str, lead_id: str
) -> dict:
    campaign = await campaign_repo.get_campaign(session, account_id, campaign_id)
    if not campaign:
        return {"status": "failed", "reason": "campaign missing"}
    if campaign.status == "paused":
        raise task.retry(countdown=3600, max_retries=None)

    step = next((s for s in campaign.steps if str(s.id) == campaign_step_id), None)
    if not step:
        return {"status": "failed", "reason": "step missing"}

    leads = await lead_repo.get_leads_by_ids(session, account_id, [lead_id])
    lead = leads[0] if leads else None
    if not lead or not lead.get("email"):
        return {"status": "failed", "reason": "lead or email missing"}
    if not consent_repo.can_send("email", lead["email_consent"]):
        return {"status": "failed", "reason": "recipient opted out"}

    retry_at = await _check_window_or_get_eta(session, account_id, "email", lead.get("country"))
    if retry_at:
        raise task.retry(eta=retry_at, max_retries=None)

    try:
        await send_gate.check(session, account_id, "email")
    except send_gate.SendBlocked as blocked:
        raise task.retry(**_retry_args(blocked))

    subject = _render(step.subject or "", lead)
    try:
        prepared = await legacy_email.prepare(
            session,
            account_id,
            to_email=lead["email"],
            body=_render(step.body or "", lead),
            lead_id=lead_id,
            source=lead.get("source"),
        )
    except legacy_email.EmailNotCompliant as exc:
        return {"status": "failed", "reason": exc.code}
    body = prepared.body
    result = send_email(lead["email"], subject, body, headers=prepared.headers)

    contact_id = uuid.UUID(lead["contact_id"]) if lead.get("contact_id") else None
    await outreach_repo.create_email_send(
        session,
        account_id,
        campaign_id=campaign.id,
        campaign_step_id=step.id,
        contact_id=contact_id,
        to_email=lead["email"],
        subject=subject,
        body=body,
        status=result["status"],
        provider_message_id=result.get("provider_id"),
        error=result.get("error"),
    )
    await outreach_repo.record_outreach_event(
        session,
        account_id,
        channel="email",
        event_type="failed" if result["status"] == "failed" else "sent",
        campaign_id=campaign_id,
        campaign_step_id=campaign_step_id,
        lead_id=lead_id,
    )
    if result["status"] in ("sent", "mock"):
        await campaign_repo.increment_counters(session, account_id, campaign_id, sent=1)
    return result


async def _send_whatsapp_impl(
    session, task, account_id: uuid.UUID, campaign_id: str, campaign_step_id: str, lead_id: str
) -> dict:
    from services.twilio_svc import send_whatsapp

    campaign = await campaign_repo.get_campaign(session, account_id, campaign_id)
    if not campaign:
        return {"status": "failed", "reason": "campaign missing"}
    if campaign.status == "paused":
        raise task.retry(countdown=3600, max_retries=None)

    step = next((s for s in campaign.steps if str(s.id) == campaign_step_id), None)
    if not step:
        return {"status": "failed", "reason": "step missing"}

    leads = await lead_repo.get_leads_by_ids(session, account_id, [lead_id])
    lead = leads[0] if leads else None
    if not lead or not lead.get("phone"):
        return {"status": "failed", "reason": "lead or phone missing"}
    if not consent_repo.can_send("whatsapp", lead["whatsapp_consent"]):
        return {"status": "failed", "reason": "recipient not opted in"}

    retry_at = await _check_window_or_get_eta(session, account_id, "whatsapp", lead.get("country"))
    if retry_at:
        raise task.retry(eta=retry_at, max_retries=None)

    try:
        await send_gate.check(session, account_id, "whatsapp")
    except send_gate.SendBlocked as blocked:
        raise task.retry(**_retry_args(blocked))

    body = _render(step.body or "", lead)
    result = send_whatsapp(lead["phone"], body)

    contact_id = uuid.UUID(lead["contact_id"]) if lead.get("contact_id") else None
    await outreach_repo.create_whatsapp_send(
        session,
        account_id,
        campaign_id=campaign.id,
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
        channel="whatsapp",
        event_type="failed" if result["status"] == "failed" else "sent",
        campaign_id=campaign_id,
        lead_id=lead_id,
    )
    if result["status"] in ("sent", "mock"):
        await campaign_repo.increment_counters(session, account_id, campaign_id, sent=1)
    return result


@celery_app.task(
    bind=True,
    name="tasks.send_tasks.send_email_task",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    max_retries=5,
    rate_limit="200/m",
)
def send_email_task(self, *, account_id: str, campaign_id: str, campaign_step_id: str, lead_id: str) -> dict:
    return run_async(
        lambda session: _send_email_impl(session, self, uuid.UUID(account_id), campaign_id, campaign_step_id, lead_id)
    )


@celery_app.task(
    bind=True,
    name="tasks.send_tasks.send_whatsapp_task",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    max_retries=5,
    rate_limit="60/m",
)
def send_whatsapp_task(self, *, account_id: str, campaign_id: str, campaign_step_id: str, lead_id: str) -> dict:
    return run_async(
        lambda session: _send_whatsapp_impl(
            session, self, uuid.UUID(account_id), campaign_id, campaign_step_id, lead_id
        )
    )
