"""Read the sending mailbox and apply what it contains: replies, hard bounces, opt-outs.

Same effects as the dry-run `simulate_event`, driven by real mail. Nothing here fabricates: a bounce suppresses the
address only on a 5.x.x delivery report; an opt-out applies only when the reply comes from the address we wrote to;
a message that does not match one of ours is counted as `unmatched` and changes nothing. Idempotent: an inbound
Message-ID is recorded once per message. The reply text is never stored beyond a 500-character excerpt.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import EmailSend, OutboundMessage
from repositories import audit_repo, campaign_repo, outbound_repo, outreach_repo, prospect_repo, suppression_repo
from services import scheduler
from services.outreach_os.inbox import InboundItem, classify

logger = logging.getLogger(__name__)


class Mailbox(Protocol):
    def fetch_unseen(self, limit: int = 50) -> list[tuple[bytes, bytes]]: ...

    def mark_seen(self, uids: list[bytes]) -> None: ...


@dataclass
class SyncResult:
    fetched: int = 0
    replies: int = 0
    opt_outs: int = 0
    bounces: int = 0
    duplicates: int = 0
    unmatched: int = 0
    ignored: int = 0

    def as_dict(self) -> dict:
        return dict(self.__dict__)


async def _match(session: AsyncSession, item: InboundItem) -> OutboundMessage | None:
    for message in await outbound_repo.find_by_provider_ids(session, item.references):
        return message
    if item.kind == "hard_bounce" and item.failed_recipient:  # a report that does not quote our Message-ID
        return await outbound_repo.latest_sent_to(session, item.failed_recipient)
    return None


async def _record_sequence_reply(
    session: AsyncSession,
    account_id: uuid.UUID,
    lead_id: uuid.UUID | None,
    *,
    inbound_id: str,
    excerpt: str,
    campaign_id: uuid.UUID | None = None,
    campaign_step_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
) -> bool:
    if inbound_id and await outreach_repo.has_inbound_message(session, account_id, inbound_id):
        return False
    if lead_id is not None:
        await outreach_repo.lock_lead_for_outreach(session, account_id, lead_id)
        if inbound_id and await outreach_repo.has_inbound_message(session, account_id, inbound_id):
            return False
    await outreach_repo.record_outreach_event(
        session,
        account_id,
        channel="email",
        event_type="replied",
        direction="inbound",
        campaign_id=str(campaign_id) if campaign_id else None,
        campaign_step_id=str(campaign_step_id) if campaign_step_id else None,
        lead_id=str(lead_id) if lead_id else None,
        contact_id=str(contact_id) if contact_id else None,
        meta={"via": "imap", "inbound_message_id": inbound_id, "excerpt": excerpt[:500]},
    )
    if campaign_id:
        await campaign_repo.increment_counters(session, account_id, str(campaign_id), replied=1)
    if lead_id is not None:
        await scheduler.cancel_lead_sequences(session, account_id, lead_id)
    return True


async def _match_campaign_send(session: AsyncSession, item: InboundItem) -> tuple[EmailSend, uuid.UUID | None] | None:
    if item.kind != "reply":
        return None
    matches = await outreach_repo.find_email_sends_by_provider_ids(session, item.references)
    return matches[0] if matches else None


async def _apply_campaign_reply(
    session: AsyncSession, item: InboundItem, send: EmailSend, lead_id: uuid.UUID | None, result: SyncResult
) -> None:
    account_id = send.account_id
    if send.status in ("bounced", "failed"):
        result.ignored += 1
        return
    same_sender = item.sender is not None and item.sender == send.to_email.lower()
    accepted = await _record_sequence_reply(
        session,
        account_id,
        lead_id,
        inbound_id=item.inbound_id,
        excerpt=item.excerpt,
        campaign_id=send.campaign_id,
        campaign_step_id=send.campaign_step_id,
        contact_id=send.contact_id,
    )
    if not accepted:
        result.duplicates += 1
        return
    send.status = "replied"
    result.replies += 1
    if item.opt_out and same_sender:
        lead = await prospect_repo.get_any(session, account_id, str(lead_id)) if lead_id else None
        if lead is not None:
            await prospect_repo.opt_out(session, account_id, lead, source="email_reply")
        await outreach_repo.record_outreach_event(
            session,
            account_id,
            channel="email",
            event_type="opted_out",
            direction="inbound",
            campaign_id=str(send.campaign_id) if send.campaign_id else None,
            campaign_step_id=str(send.campaign_step_id) if send.campaign_step_id else None,
            lead_id=str(lead_id) if lead_id else None,
            contact_id=str(send.contact_id) if send.contact_id else None,
            meta={"via": "imap", "inbound_message_id": item.inbound_id},
        )
        result.opt_outs += 1


async def _apply(session: AsyncSession, item: InboundItem, message: OutboundMessage, result: SyncResult) -> None:
    account_id = message.account_id
    if item.inbound_id and await outbound_repo.has_inbound_event(session, message.id, item.inbound_id):
        result.duplicates += 1
        return
    detail = {"via": "imap", "inbound_message_id": item.inbound_id}
    if item.kind == "hard_bounce":
        if item.failed_recipient != (message.to_email or "").lower():
            result.ignored += 1  # the report is about another address: never suppress on a mismatch
            return
        message.status = "bounced"
        await outbound_repo.add_event(session, account_id, message.id, "bounced", {**detail, "kind": "hard"})
        await suppression_repo.add(session, account_id, "email", item.failed_recipient, reason="bounce")
        result.bounces += 1
        action = "message.bounced"
    else:
        if message.status == "sent":
            message.status = "replied"
        same_sender = item.sender is not None and item.sender == (message.to_email or "").lower()
        await outbound_repo.add_event(
            session,
            account_id,
            message.id,
            "replied",
            {**detail, "excerpt": item.excerpt, "sender_matches_recipient": same_sender},
        )
        await _record_sequence_reply(
            session,
            account_id,
            message.lead_id,
            inbound_id=item.inbound_id,
            excerpt=item.excerpt,
        )
        result.replies += 1
        if item.opt_out and same_sender:  # a STOP from someone else is flagged for a human, not applied
            lead = await prospect_repo.get_any(session, account_id, str(message.lead_id))
            if lead is not None:
                await prospect_repo.opt_out(session, account_id, lead, source="email_reply")
            await outbound_repo.add_event(session, account_id, message.id, "opted_out", {**detail, "via": "reply"})
            result.opt_outs += 1
        action = "message.replied"
    await audit_repo.log(
        session,
        account_id,
        action=action,
        resource_type="outbound_message",
        resource_id=message.id,
        actor_type="system",
        diff={"via": "imap"},  # never the reply text
    )


async def sync(session: AsyncSession, mailbox: Mailbox, limit: int = 50) -> SyncResult:
    """Fetch, apply, commit, then flag as read (in that order: a crash re-reads and de-duplicates, never loses mail)."""
    result = SyncResult()
    batch = await asyncio.to_thread(mailbox.fetch_unseen, limit)
    result.fetched = len(batch)
    for _, raw in batch:
        item = classify(raw)
        if item.kind == "ignore":
            result.ignored += 1
            continue
        message = await _match(session, item)
        if message is not None:
            await _apply(session, item, message, result)
            continue
        campaign_send = await _match_campaign_send(session, item)
        if campaign_send is None:
            result.unmatched += 1
            continue
        send, lead_id = campaign_send
        await _apply_campaign_reply(session, item, send, lead_id, result)
    await session.commit()
    await asyncio.to_thread(mailbox.mark_seen, [uid for uid, _ in batch])
    return result
