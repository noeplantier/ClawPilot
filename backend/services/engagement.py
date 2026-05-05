"""Dynamic lead conversion engine.

Applies engagement events (delivered/opened/clicked/replied/bounced/unsubscribed)
to a lead and atomically:
  * updates the lead's score (clamped 0..100)
  * progresses pipeline stage (forward-only, unless bounce/unsubscribed which forces 'lost')
  * marks suppressed=true on hard-fail events
  * logs an activity row
  * bumps the relevant campaign counter (opened / replied)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid


STAGE_ORDER = ["new", "contacted", "engaged", "qualified", "won", "lost"]


# event_type -> { score_delta, target_stage, force_stage, suppress }
RULES = {
    "delivered":    {"score": 1,   "stage": "contacted", "force": False},
    "opened":       {"score": 5,   "stage": "contacted", "force": False},
    "clicked":      {"score": 10,  "stage": "engaged",   "force": False},
    "replied":      {"score": 30,  "stage": "qualified", "force": False},
    "bounced":      {"score": -20, "stage": "lost",      "force": True,  "suppress": True},
    "unsubscribed": {"score": -50, "stage": "lost",      "force": True,  "suppress": True},
    "spam":         {"score": -40, "stage": "lost",      "force": True,  "suppress": True},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def apply(
    db,
    lead_id: str,
    event: str,
    channel: str = "email",
    campaign_id: Optional[str] = None,
) -> Optional[dict]:
    """Apply engagement event to a lead. Returns updated lead dict or None."""
    rule = RULES.get(event)
    if not rule:
        return None

    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        return None

    # Suppressed leads are frozen from positive engagement (still allow negative)
    if lead.get("suppressed") and not rule.get("force"):
        return lead

    updates = {}

    # Score (clamped 0..100)
    current_score = int(lead.get("score") or 0)
    new_score = max(0, min(100, current_score + rule["score"]))
    if new_score != current_score:
        updates["score"] = new_score

    # Stage progression
    current_stage = lead.get("stage", "new")
    target_stage = rule["stage"]
    progressed = False
    try:
        cur_idx = STAGE_ORDER.index(current_stage)
    except ValueError:
        cur_idx = 0
    try:
        tgt_idx = STAGE_ORDER.index(target_stage)
    except ValueError:
        tgt_idx = cur_idx

    if rule.get("force"):
        if current_stage != target_stage:
            updates["stage"] = target_stage
            progressed = True
    elif tgt_idx > cur_idx:
        updates["stage"] = target_stage
        progressed = True

    if rule.get("suppress"):
        updates["suppressed"] = True

    if updates:
        await db.leads.update_one({"id": lead_id}, {"$set": updates})

    # Activity log
    parts = [f"{lead.get('full_name')} → {event}"]
    if "score" in updates:
        parts.append(f"score {current_score}→{new_score}")
    if progressed:
        parts.append(f"stage → {target_stage}")
    if rule.get("suppress"):
        parts.append("(suppressed)")

    await db.activity.insert_one({
        "id": str(uuid.uuid4()),
        "org_id": lead["org_id"],
        "kind": f"engagement.{event}",
        "title": " · ".join(parts),
        "meta": {
            "lead_id": lead_id,
            "campaign_id": campaign_id,
            "event": event,
            "channel": channel,
            "score_delta": rule["score"],
            "score": new_score,
            "stage": updates.get("stage", current_stage),
            "progressed": progressed,
        },
        "created_at": _now_iso(),
    })

    # Campaign counters
    if campaign_id:
        counter_field = None
        if event in ("opened", "clicked"):
            counter_field = "opened"
        elif event == "replied":
            counter_field = "replied"
        if counter_field:
            await db.campaigns.update_one(
                {"id": campaign_id, "org_id": lead["org_id"]},
                {"$inc": {counter_field: 1}},
            )

    # Auto-mark won when reaching qualified + a positive event chain (heuristic)
    new_stage = updates.get("stage", current_stage)
    if new_stage == "qualified" and new_score >= 90:
        await db.leads.update_one({"id": lead_id}, {"$set": {"stage": "won"}})
        await db.activity.insert_one({
            "id": str(uuid.uuid4()),
            "org_id": lead["org_id"],
            "kind": "engagement.won",
            "title": f"🏆 {lead.get('full_name')} converted (score {new_score})",
            "meta": {"lead_id": lead_id, "campaign_id": campaign_id},
            "created_at": _now_iso(),
        })
        if campaign_id:
            await db.campaigns.update_one(
                {"id": campaign_id, "org_id": lead["org_id"]},
                {"$inc": {"converted": 1}},
            )
        updates["stage"] = "won"

    return {**lead, **updates}


async def remove_from_active_campaigns(db, lead_id: str, org_id: str) -> int:
    """When a lead is suppressed, also cancel any pending scheduled jobs for them."""
    res = await db.scheduled_jobs.delete_many({
        "lead_id": lead_id,
        "org_id": org_id,
        "status": "pending",
    })
    return res.deleted_count
