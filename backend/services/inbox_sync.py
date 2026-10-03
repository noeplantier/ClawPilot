"""Read the sending mailbox and apply what it contains: replies, hard bounces, opt-outs.

Same effects as the dry-run `simulate_event`, driven by real mail. Nothing here fabricates: a bounce suppresses the
address only on a 5.x.x delivery report; an opt-out applies only when the reply comes from the address we wrote to;
a message that does not match one of ours is counted as `unmatched` and changes nothing. Idempotent: an inbound
Message-ID is recorded once per message. The reply text is never stored beyond a 500-character excerpt.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import OutboundMessage
from repositories import audit_repo, outbound_repo, prospect_repo, suppression_repo
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
        if message is None:
            result.unmatched += 1
            continue
        await _apply(session, item, message, result)
    await session.commit()
    await asyncio.to_thread(mailbox.mark_seen, [uid for uid, _ in batch])
    return result
