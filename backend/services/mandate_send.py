"""Automatic send queue for active mandates.

No new queue table: the plan is derived from what really exists — Hot Leads staged by discovery, ready draft jobs,
approved drafts and the append-only outbound ledger. Every message goes through `outreach_os.dispatch.dispatch_draft`,
the single enforcement point shared with the other send paths (kill switch, pause, suppression, consent, compliance,
sender identity, unsubscribe, limits, sandbox, one recipient). 'accepted' means the channel adapter took the message;
it is never presented as a delivery. A row left `sending` is never retried blindly.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import MessageDraft, OutboundMessage
from db.models.prospect import DraftJob
from db.models.prospecting import Mandate, ProspectingBatch, ProspectingBatchItem
from repositories import audit_repo, launch_repo, outbound_repo, send_policy_repo
from services import feature_flags, imap_svc, send_gate
from services.outreach_os import dispatch

MAX_PER_RUN = 20
STOP_TO_STATUS = {
    "expired": "expired",
    "kill_switch": "revoked",
    "paused": "paused",
    "hard_bounce": "revoked",
    "opposition": "revoked",
    "provider_failure": "revoked",
    "reply": "paused",
    "ai_budget_reached": "paused",
    "daily_volume_reached": "paused",
    "total_volume_reached": "paused",
    "reply_collection_unavailable": "paused",
}
MESSAGE_STATE = {
    "sending": "processing",  # outcome unknown: a person reconciles from the mailbox, never a blind retry
    "sent": "accepted",  # the adapter accepted it — NOT a delivery confirmation
    "failed": "failed",
    "bounced": "bounced",
    "replied": "reply",
}
QUEUE_STATES = ("planned", "processing", "accepted", "failed", "bounced", "reply")

Dispatcher = Callable[..., Awaitable[tuple[OutboundMessage, bool]]]


def in_window(mandate: Mandate, now: datetime) -> bool:
    """The mandate's own UTC windows; an empty configuration authorises nothing."""
    hour = now.astimezone(timezone.utc).hour
    return any(
        isinstance(w, dict)
        and isinstance(w.get("start_hour"), int)
        and isinstance(w.get("end_hour"), int)
        and w["start_hour"] <= hour < w["end_hour"]
        for w in (mandate.time_windows or [])
    )


async def hot_lead_ids(session: AsyncSession, account_id: uuid.UUID, mandate_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        (
            await session.execute(
                select(ProspectingBatchItem.lead_id)
                .join(ProspectingBatch, ProspectingBatchItem.batch_id == ProspectingBatch.id)
                .where(
                    ProspectingBatch.account_id == account_id,
                    ProspectingBatch.config["mandate_id"].astext == str(mandate_id),
                    ProspectingBatchItem.stage == "hot",
                    ProspectingBatchItem.lead_id.is_not(None),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )


async def _messages(session: AsyncSession, account_id: uuid.UUID, lead_ids: list[uuid.UUID]) -> list[OutboundMessage]:
    if not lead_ids:
        return []
    return list(
        (
            await session.execute(
                select(OutboundMessage).where(
                    OutboundMessage.account_id == account_id, OutboundMessage.lead_id.in_(lead_ids)
                )
            )
        )
        .scalars()
        .all()
    )


async def _ready_drafts(session: AsyncSession, account_id: uuid.UUID, lead_ids: list[uuid.UUID]) -> list[MessageDraft]:
    if not lead_ids:
        return []
    draft_ids = (
        (
            await session.execute(
                select(DraftJob.draft_id).where(
                    DraftJob.account_id == account_id,
                    DraftJob.lead_id.in_(lead_ids),
                    DraftJob.status == "ready",
                    DraftJob.draft_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not draft_ids:
        return []
    return list(
        (
            await session.execute(
                select(MessageDraft).where(
                    MessageDraft.account_id == account_id,
                    MessageDraft.id.in_(draft_ids),
                    MessageDraft.status == "approved",  # quality control: an unreviewed draft never leaves
                )
            )
        )
        .scalars()
        .all()
    )


async def snapshot(session: AsyncSession, mandate: Mandate, now: datetime) -> tuple[dict, list[MessageDraft]]:
    """Real queue states for this mandate plus the approved drafts still waiting to be planned."""
    counts = {state: 0 for state in QUEUE_STATES}
    leads = await hot_lead_ids(session, mandate.account_id, mandate.id)
    messages = await _messages(session, mandate.account_id, leads)
    drafts = await _ready_drafts(session, mandate.account_id, leads)
    of_draft = {draft.id: draft for draft in drafts}
    handled: set[uuid.UUID] = set()
    planned: list[MessageDraft] = []
    for draft in drafts:
        attempts = [m for m in messages if m.draft_id == draft.id]
        if not attempts:
            counts["planned"] += 1
            planned.append(draft)
            continue
        latest = max(attempts, key=lambda m: m.dispatched_at)
        handled.add(latest.id)
        counts[MESSAGE_STATE.get(latest.status, "failed")] += 1
    for message in messages:  # messages from older drafts still tell the truth about this mandate
        if message.id not in handled:
            counts[MESSAGE_STATE.get(message.status, "failed")] += 1
    return counts, planned


async def stop_reason(session: AsyncSession, mandate: Mandate, now: datetime) -> Optional[str]:
    """Pure read: why this mandate must not send another message, or None while it may. No state is changed here."""
    if mandate.status in ("paused", "revoked", "expired"):
        return mandate.status
    if mandate.expires_at <= now:
        return "expired"
    if feature_flags.kill_switch():
        return "kill_switch"
    policy = await send_policy_repo.get_policy(session, mandate.account_id, "email")
    if policy.sending_paused:
        return "paused"
    # A STOP reply cannot be collected without a mailbox: say so instead of pretending the stream is healthy.
    if not imap_svc.is_configured():
        return "reply_collection_unavailable"

    leads = await hot_lead_ids(session, mandate.account_id, mandate.id)
    messages = await _messages(session, mandate.account_id, leads)
    if any(m.status == "replied" for m in messages):
        return "reply"
    if await launch_repo.opted_out_message_lead_ids(session, mandate.account_id, leads):
        return "opposition"
    if any(m.status == "bounced" for m in messages):
        return "hard_bounce"
    if any(m.status == "failed" for m in messages):
        return "provider_failure"

    ready = await _ready_drafts(session, mandate.account_id, leads)
    if len(ready) >= int(mandate.ai_budget or 0):
        return "ai_budget_reached"

    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    sent = [m for m in messages if m.status in ("sent", "replied", "bounced")]
    if len([m for m in sent if m.dispatched_at >= day_start]) >= mandate.daily_volume:
        return "daily_volume_reached"
    if len(sent) >= mandate.total_volume:
        return "total_volume_reached"
    return None


async def apply_stop(session: AsyncSession, mandate: Mandate, reason: str, now: datetime) -> str:
    """Persist the automatic stop and its action journal. Only a status that expresses 'stops sending' is used."""
    target = STOP_TO_STATUS.get(reason, "paused")
    mandate.status = target
    mandate.updated_at = now  # the live snapshot's version follows the stop
    await audit_repo.log(
        session,
        mandate.account_id,
        action="mandate.auto_stop",
        resource_type="mandate",
        resource_id=mandate.id,
        actor_type="system",
        diff={"reason": reason, "status": target, "at": now.isoformat()},
    )
    return target


async def live_streams(session: AsyncSession, mandate: Mandate, now: datetime) -> dict:
    """Only real, mandate-attributed data; an unconfigured signal is reported as such, never as a healthy zero."""
    counts, _ = await snapshot(session, mandate, now)
    leads = await hot_lead_ids(session, mandate.account_id, mandate.id)
    messages = await _messages(session, mandate.account_id, leads)
    return {
        "send_queue": {"available": True, **counts},
        "replies": {"available": True, "count": len([m for m in messages if m.status == "replied"])},
        "oppositions": {
            "available": True,
            "count": len(await launch_repo.opted_out_message_lead_ids(session, mandate.account_id, leads)),
        },
        "reply_collection": {"available": bool(imap_svc.is_configured()), "configured": bool(imap_svc.is_configured())},
        "stop_reason": await stop_reason(session, mandate, now),
    }


async def send_due(
    session: AsyncSession,
    *,
    now: datetime,
    live_adapter=None,
    dispatcher: Dispatcher = dispatch.dispatch_draft,
    max_per_run: int = MAX_PER_RUN,
) -> dict[str, int]:
    """Plan and send what is due for every active mandate. Never raises for one message; never retries an unclear send."""
    counts: Counter = Counter()
    mandates = (
        (
            await session.execute(
                select(Mandate).where(Mandate.status == "active", Mandate.expires_at > now).order_by(Mandate.created_at)
            )
        )
        .scalars()
        .all()
    )
    for mandate in mandates:
        reason = await stop_reason(session, mandate, now)
        if reason:
            await apply_stop(session, mandate, reason, now)
            counts["stopped"] += 1
            continue
        if not in_window(mandate, now):
            counts["outside_window"] += 1
            continue
        queue_counts, planned = await snapshot(session, mandate, now)
        account_halted = False
        for draft in planned[:max_per_run]:
            # `get_for_draft` ignores failed attempts but keeps `sending`/unknown ones: no blind retry.
            if await outbound_repo.get_for_draft(session, mandate.account_id, draft.id) is not None:
                counts["already"] += 1
                continue
            failed = await outbound_repo.count_failed_for_draft(session, mandate.account_id, draft.id)
            key = f"mandate:{mandate.id}:{draft.id}" + (f":retry{failed}" if failed else "")
            try:
                message, _ = await dispatcher(
                    session,
                    mandate.account_id,
                    draft,
                    now=now,
                    user_id=None,
                    idempotency_key=key,
                    live_adapter=live_adapter,
                )
            except dispatch.DispatchBlocked as blocked:
                counts["blocked"] += 1
                await audit_repo.log(
                    session,
                    mandate.account_id,
                    action="mandate.send_blocked",
                    resource_type="mandate",
                    resource_id=mandate.id,
                    actor_type="system",
                    diff={"code": blocked.code, "draft_id": str(draft.id)},
                )
                if blocked.code in ("kill_switch", "paused", "limit_daily", "limit_hourly", "limit_delay"):
                    account_halted = True
                    break
                continue
            state = MESSAGE_STATE.get(message.status, "failed")
            counts[state] += 1
        counts.update({f"queue_{k}": v for k, v in queue_counts.items()})
        if not account_halted:
            after = await stop_reason(session, mandate, now)
            if after:
                await apply_stop(session, mandate, after, now)
                counts["stopped"] += 1
    return dict(counts)


async def daily_report(session: AsyncSession, *, now: datetime) -> dict[str, int]:
    """Compact, real daily journal entry per mandate that ran or is still active."""
    from_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    mandates = (
        (await session.execute(select(Mandate).where(Mandate.status.in_(("active", "paused", "expired", "revoked")))))
        .scalars()
        .all()
    )
    reported = 0
    for mandate in mandates:
        leads = await hot_lead_ids(session, mandate.account_id, mandate.id)
        messages = await _messages(session, mandate.account_id, leads)
        recent = [m for m in messages if m.dispatched_at >= from_date]
        diff = {
            "date": from_date.date().isoformat(),
            "accepted": len([m for m in recent if m.status in ("sent", "replied", "bounced")]),
            "failed": len([m for m in recent if m.status == "failed"]),
            "replies": len([m for m in recent if m.status == "replied"]),
            "bounces": len([m for m in recent if m.status == "bounced"]),
            "status": mandate.status,
        }
        await audit_repo.log(
            session,
            mandate.account_id,
            action="mandate.daily_report",
            resource_type="mandate",
            resource_id=mandate.id,
            actor_type="system",
            diff=diff,
        )
        reported += 1
    return {"mandates_reported": reported}
