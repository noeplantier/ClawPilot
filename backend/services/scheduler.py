"""In-process async scheduler for delayed campaign steps.

Polls MongoDB every ~10s for due jobs and executes them via the same
send_email / send_whatsapp services, with the same {{token}} rendering.

Collection: scheduled_jobs
  { id, org_id, campaign_id, step_index, lead_id, run_at (iso), status: pending|running|done|failed, error }
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List

from deps import db
from services.sendgrid_svc import send_email
from services.twilio_svc import send_whatsapp

logger = logging.getLogger("openclaw.scheduler")

POLL_INTERVAL = 10  # seconds
_task: asyncio.Task | None = None


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


async def enqueue_campaign(campaign_id: str, org_id: str) -> dict:
    """Schedule every step × every assigned lead with cumulative delays."""
    c = await db.campaigns.find_one({"id": campaign_id, "org_id": org_id}, {"_id": 0})
    if not c:
        return {"scheduled": 0, "error": "campaign not found"}
    leads = c.get("lead_ids") or []
    steps = c.get("steps") or []
    if not leads or not steps:
        return {"scheduled": 0, "error": "no leads or steps"}

    now = datetime.now(timezone.utc)
    cumulative = 0
    docs: List[dict] = []
    for idx, step in enumerate(steps):
        cumulative += int(step.get("delay_hours") or 0)
        run_at = now + timedelta(hours=cumulative)
        for lead_id in leads:
            docs.append({
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "campaign_id": campaign_id,
                "step_index": idx,
                "lead_id": lead_id,
                "run_at": run_at.isoformat(),
                "status": "pending",
                "error": None,
                "created_at": now.isoformat(),
            })

    if docs:
        await db.scheduled_jobs.insert_many(docs)
    return {"scheduled": len(docs), "steps": len(steps), "leads": len(leads)}


async def pending_for_campaign(campaign_id: str, org_id: str) -> List[dict]:
    cursor = db.scheduled_jobs.find(
        {"campaign_id": campaign_id, "org_id": org_id}, {"_id": 0}
    ).sort("run_at", 1).limit(500)
    return await cursor.to_list(500)


async def cancel_campaign(campaign_id: str, org_id: str) -> int:
    res = await db.scheduled_jobs.delete_many({
        "campaign_id": campaign_id,
        "org_id": org_id,
        "status": "pending",
    })
    return res.deleted_count


async def _execute_job(job: dict) -> None:
    """Run a single scheduled job. Caller already marked it running."""
    c = await db.campaigns.find_one({"id": job["campaign_id"], "org_id": job["org_id"]}, {"_id": 0})
    if not c:
        await db.scheduled_jobs.update_one({"id": job["id"]}, {"$set": {"status": "failed", "error": "campaign missing"}})
        return

    # Respect pause
    if c.get("status") == "paused":
        # re-queue: set status back to pending, shift run_at by 1h
        new_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        await db.scheduled_jobs.update_one(
            {"id": job["id"]}, {"$set": {"status": "pending", "run_at": new_at}}
        )
        return

    steps = c.get("steps") or []
    if job["step_index"] >= len(steps):
        await db.scheduled_jobs.update_one({"id": job["id"]}, {"$set": {"status": "failed", "error": "step out of range"}})
        return
    step = steps[job["step_index"]]

    lead = await db.leads.find_one({"id": job["lead_id"], "org_id": job["org_id"]}, {"_id": 0})
    if not lead:
        await db.scheduled_jobs.update_one({"id": job["id"]}, {"$set": {"status": "failed", "error": "lead missing"}})
        return

    channel = step.get("channel", "email")
    body = _render(step.get("body") or "", lead)
    subject = _render(step.get("subject") or "", lead) if channel == "email" else None

    if channel == "email":
        if not lead.get("email"):
            await db.scheduled_jobs.update_one({"id": job["id"]}, {"$set": {"status": "failed", "error": "no email"}})
            return
        result = send_email(lead["email"], subject or "", body)
        to = lead["email"]
    else:
        if not lead.get("phone"):
            await db.scheduled_jobs.update_one({"id": job["id"]}, {"$set": {"status": "failed", "error": "no phone"}})
            return
        result = send_whatsapp(lead["phone"], body)
        to = lead["phone"]

    msg_id = str(uuid.uuid4())
    await db.messages.insert_one({
        "id": msg_id,
        "org_id": job["org_id"],
        "campaign_id": job["campaign_id"],
        "lead_id": lead["id"],
        "channel": channel,
        "direction": "outbound",
        "to": to,
        "subject": subject,
        "body": body,
        "status": result["status"],
        "provider_id": result.get("provider_id"),
        "error": result.get("error"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    if result["status"] in ("sent", "mock"):
        await db.campaigns.update_one(
            {"id": job["campaign_id"], "org_id": job["org_id"]},
            {"$inc": {"sent": 1}},
        )

    await db.scheduled_jobs.update_one(
        {"id": job["id"]},
        {"$set": {"status": "done", "executed_at": datetime.now(timezone.utc).isoformat()}},
    )


async def _loop() -> None:
    logger.info("Scheduler loop started (poll=%ss)", POLL_INTERVAL)
    while True:
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            # Atomically claim pending jobs that are due
            batch: List[dict] = []
            while len(batch) < 50:
                job = await db.scheduled_jobs.find_one_and_update(
                    {"status": "pending", "run_at": {"$lte": now_iso}},
                    {"$set": {"status": "running", "claimed_at": now_iso}},
                    projection={"_id": 0},
                    return_document=True,
                )
                if not job:
                    break
                batch.append(job)

            for job in batch:
                try:
                    await _execute_job(job)
                except Exception as e:
                    logger.exception("job execution failed: %s", e)
                    await db.scheduled_jobs.update_one(
                        {"id": job["id"]}, {"$set": {"status": "failed", "error": str(e)[:240]}}
                    )
        except Exception as outer:
            logger.exception("scheduler loop error: %s", outer)

        await asyncio.sleep(POLL_INTERVAL)


def start() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
