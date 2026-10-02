"""Dispatch of an approved draft through a channel adapter — dry-run only in this slice.

Order of checks (the first failure wins, nothing is written for a refused attempt except the caller's audit entry):
kill switch → account pause → draft/prospect eligibility → suppression and consent → compliance of the content →
send limits → adapter. A replay with the same idempotency key returns the original message and sends nothing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Lead, MessageDraft, OutboundMessage
from repositories import (
    audit_repo,
    consent_repo,
    outbound_repo,
    prospect_repo,
    suppression_repo,
    usage_repo,
)
from services import feature_flags, send_gate
from services.outreach_os import channels, drafts
from services.outreach_os.normalize import normalize_domain, normalize_email, normalize_phone
from services.outreach_os.replies import is_opt_out

CHANNEL = "email"
REPLY_EXCERPT_CHARS = 500


# The refusal type and the shared checks live in services/send_gate.py (used by every send path).
DispatchBlocked = send_gate.SendBlocked


async def _assert_eligible(
    session: AsyncSession, account_id: uuid.UUID, draft: MessageDraft, lead: Optional[Lead]
) -> Lead:
    if draft.status != "approved":
        raise DispatchBlocked("draft_not_approved", f"Draft is '{draft.status}': a human must approve it first")
    if lead is None or lead.id != draft.lead_id:
        raise DispatchBlocked("prospect_gone", "The prospect no longer exists")
    if lead.review_status != "approved":
        raise DispatchBlocked("prospect_not_approved", f"Prospect review status is '{lead.review_status}'")
    if not lead.email:
        raise DispatchBlocked("no_email", "Prospect has no e-mail address")
    if await suppression_repo.is_suppressed(
        session,
        account_id,
        email=normalize_email(lead.email),
        phone=normalize_phone(lead.phone),
        domain=normalize_domain(lead.website),
    ):
        raise DispatchBlocked("suppressed", "Prospect is on the suppression list")
    contact_id = await consent_repo.get_primary_contact_id(session, lead.id)
    if contact_id is not None:
        status = await consent_repo.get_status(session, contact_id, CHANNEL)
        if not consent_repo.can_send(CHANNEL, status):
            raise DispatchBlocked("opted_out", "Prospect opted out of e-mail")
    return lead


async def dispatch_draft(
    session: AsyncSession,
    account_id: uuid.UUID,
    draft: MessageDraft,
    *,
    now: datetime,
    user_id: Optional[uuid.UUID],
    idempotency_key: Optional[str] = None,
) -> tuple[OutboundMessage, bool]:
    """Returns (message, newly_created). Raises `DispatchBlocked` when the attempt must not go through."""
    key = idempotency_key or f"dispatch:{draft.id}"
    existing = await outbound_repo.get_by_key(session, account_id, key) or await outbound_repo.get_for_draft(
        session, account_id, draft.id
    )  # one draft produces at most one message, whatever the key
    if existing is not None:
        return existing, False

    await send_gate.lock_and_assert_not_halted(session, account_id, CHANNEL)

    lead = await prospect_repo.get(session, account_id, str(draft.lead_id))
    lead = await _assert_eligible(session, account_id, draft, lead)
    recipient = lead.email
    assert recipient is not None  # guaranteed by _assert_eligible

    sender = drafts.SenderIdentity.from_env()
    if sender is None:
        raise DispatchBlocked("sender_not_configured", "Sender identity is not configured")
    problems = drafts.compliance_problems(draft.body, sender)
    unsubscribe_url = channels.find_unsubscribe_url(draft.body)
    if problems or unsubscribe_url is None:
        raise DispatchBlocked(
            "not_compliant", f"Draft is not compliant: {', '.join(problems) or 'no unsubscribe link'}"
        )

    await send_gate.assert_within_limits(session, account_id, CHANNEL, now)

    try:
        adapter = channels.select_adapter(CHANNEL, live_sending_enabled=not feature_flags.dry_run())
    except channels.LiveSendingNotAvailable as exc:
        raise DispatchBlocked("live_not_available", str(exc))
    result = adapter.send(
        channels.ChannelMessage(
            to=recipient,
            subject=draft.subject,
            body=draft.body,
            sender_name=sender.name,
            sender_email=sender.reply_to,
            idempotency_key=key,
            headers=channels.unsubscribe_headers(unsubscribe_url),
        )
    )
    message, created = await outbound_repo.create_idempotent(
        session,
        account_id,
        idempotency_key=key,
        lead_id=lead.id,
        draft_id=draft.id,
        channel=CHANNEL,
        to_email=normalize_email(lead.email),
        subject=draft.subject,
        body=draft.body,
        adapter=adapter.name,
        dry_run=adapter.dry_run,
        status=result.status,
        provider_message_id=result.provider_id,
        error=result.error,
        dispatched_at=now,
    )
    if created:
        await outbound_repo.add_event(
            session,
            account_id,
            message.id,
            "sent" if result.status == "sent" else "failed",
            {"adapter": adapter.name, "dry_run": adapter.dry_run, "list_unsubscribe": True, "error": result.error},
        )
        if result.status == "sent":
            await usage_repo.record(session, account_id, "messages_dispatched", 1, {"dry_run": adapter.dry_run})
        await audit_repo.log(
            session,
            account_id,
            action="message.dispatched" if result.status == "sent" else "message.failed",
            resource_type="outbound_message",
            resource_id=message.id,
            actor_type="user" if user_id else "system",
            actor_user_id=user_id,
            diff={"prospect_id": str(lead.id), "draft_id": str(draft.id), "dry_run": adapter.dry_run},
        )
    return message, created


async def simulate_event(
    session: AsyncSession,
    account_id: uuid.UUID,
    message: OutboundMessage,
    *,
    event: str,
    text: Optional[str],
    user_id: Optional[uuid.UUID],
) -> OutboundMessage:
    """Dry-run stand-in for the provider webhook: a hard bounce or a reply. Same effects a real one would have."""
    if not message.dry_run:
        raise DispatchBlocked("not_simulated", "Only dry-run messages can be simulated")
    if message.status == "bounced":
        raise DispatchBlocked("already_bounced", "Message already bounced")
    if message.status == "failed":
        raise DispatchBlocked("not_delivered", "Message was never sent")

    if event == "bounced":
        message.status = "bounced"
        await outbound_repo.add_event(session, account_id, message.id, "bounced", {"kind": "hard", "simulated": True})
        if message.to_email:  # a hard bounce means the address is dead: never write to it again
            await suppression_repo.add(session, account_id, "email", message.to_email, reason="bounce")
    else:
        message.status = "replied"
        excerpt = (text or "")[:REPLY_EXCERPT_CHARS]
        await outbound_repo.add_event(
            session, account_id, message.id, "replied", {"simulated": True, "excerpt": excerpt}
        )
        if is_opt_out(text or ""):
            lead = await prospect_repo.get(session, account_id, str(message.lead_id))
            if lead is not None:
                await prospect_repo.opt_out(session, account_id, lead, source="email_reply")
            await outbound_repo.add_event(session, account_id, message.id, "opted_out", {"via": "reply"})
    await session.flush()
    await audit_repo.log(
        session,
        account_id,
        action=f"message.{event}",
        resource_type="outbound_message",
        resource_id=message.id,
        actor_type="user" if user_id else "system",
        actor_user_id=user_id,
        diff={"simulated": True},  # never the reply text
    )
    return message
