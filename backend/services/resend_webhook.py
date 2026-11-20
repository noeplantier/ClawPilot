"""Apply Resend's signed events to the messages Resend carried: permanent bounces and spam complaints.

Under Resend the bounce report goes back to Resend, not to the sending mailbox, so `inbox_sync` never sees it: without
these events the mandate's bounce-rate stop could not trip. Same effects as the IMAP path, nothing invented:

- `email.bounced` with `bounce.type == "Permanent"` only: the message is `bounced`, a `bounced` event is recorded and
  the address is suppressed. A transient or undetermined bounce changes nothing.
- `email.complained`: the prospect is opted out (as a STOP reply) and an `opted_out` event is recorded, which counts
  in the mandate's opposition rate.
- The message is found by the id Resend returned (`provider_message_id`), only among messages Resend carried, and the
  event's recipient must be the message's: on a mismatch nothing changes. An event id is applied once (idempotent).
- Every other event (sent, delivered, opened…) is ignored: "delivered" has no status here and is never claimed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repositories import audit_repo, outbound_repo, prospect_repo, suppression_repo
from services.outreach_os.normalize import normalize_email

HANDLED = ("email.bounced", "email.complained")


async def apply(session: AsyncSession, event: dict[str, Any], event_id: str) -> str:
    """What the event did, as a short code (for the response and the log; never the recipient)."""
    kind = event.get("type")
    if kind not in HANDLED:
        return "ignored"
    raw_data = event.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    email_id = str(data.get("email_id") or "")
    if not email_id:
        return "no_email_id"
    message = next(
        (m for m in await outbound_repo.find_by_provider_ids(session, [email_id]) if m.adapter == "resend"), None
    )
    if message is None:
        return "unmatched"
    recipients = {normalize_email(str(to)) for to in (data.get("to") or []) if isinstance(to, str)}
    address = normalize_email(message.to_email or "")
    if address is None or address not in recipients:
        return "recipient_mismatch"  # never suppress or opt out on a report about another address
    if await outbound_repo.has_inbound_event(session, message.id, event_id):
        return "duplicate"
    detail = {"via": "resend", "inbound_message_id": event_id}
    if kind == "email.bounced":
        raw_bounce = data.get("bounce")
        bounce: dict[str, Any] = raw_bounce if isinstance(raw_bounce, dict) else {}
        if bounce.get("type") != "Permanent":
            return "not_permanent"
        message.status = "bounced"
        sub_type = str(bounce.get("subType") or "")[:40]
        await outbound_repo.add_event(
            session, message.account_id, message.id, "bounced", {**detail, "kind": "hard", "sub_type": sub_type}
        )
        await suppression_repo.add(session, message.account_id, "email", address, reason="bounce")
        action, outcome = "message.bounced", "bounced"
    else:
        lead = await prospect_repo.get_any(session, message.account_id, str(message.lead_id))
        if lead is not None:
            await prospect_repo.opt_out(session, message.account_id, lead, source="email_complaint")
        await outbound_repo.add_event(
            session, message.account_id, message.id, "opted_out", {**detail, "kind": "complaint"}
        )
        action, outcome = "message.complained", "opted_out"
    await audit_repo.log(
        session,
        message.account_id,
        action=action,
        resource_type="outbound_message",
        resource_id=message.id,
        actor_type="system",
        diff={"via": "resend"},
    )
    return outcome
