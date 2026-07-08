"""Consent persistence — append-only `consent_records` ledger + denormalized
`consent_current` for the send-path hot read (plan doc section 1.7).

Enforcement policy (deliberately asymmetric, matching the brief's actual wording
-- "aucun envoi WhatsApp sans opt-in explicite" for WhatsApp, general opt-out
respect elsewhere):
  - WhatsApp: STRICT — only 'opted_in' may be sent to.
  - Email: PERMISSIVE — anything except 'opted_out' may be sent to.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Contact
from db.models.consent import ConsentCurrent, ConsentRecord

DEFAULT_STATUS = "unknown"


async def get_status(session: AsyncSession, contact_id: uuid.UUID, channel: str) -> str:
    result = await session.execute(
        select(ConsentCurrent.status).where(ConsentCurrent.contact_id == contact_id, ConsentCurrent.channel == channel)
    )
    return result.scalar_one_or_none() or DEFAULT_STATUS


async def get_status_map(session: AsyncSession, contact_ids: list[uuid.UUID], channel: str) -> dict[uuid.UUID, str]:
    """Bulk lookup for batch sends — avoids one query per lead."""
    if not contact_ids:
        return {}
    result = await session.execute(
        select(ConsentCurrent.contact_id, ConsentCurrent.status).where(
            ConsentCurrent.contact_id.in_(contact_ids), ConsentCurrent.channel == channel
        )
    )
    return {contact_id: status for contact_id, status in result.all()}


def can_send(channel: str, status: str) -> bool:
    if channel == "whatsapp":
        return status == "opted_in"
    return status != "opted_out"


async def record_consent(
    session: AsyncSession,
    account_id: uuid.UUID,
    contact_id: uuid.UUID,
    *,
    channel: str,
    status: str,
    source: str,
    evidence: Optional[dict] = None,
) -> ConsentRecord:
    record = ConsentRecord(
        account_id=account_id,
        contact_id=contact_id,
        channel=channel,
        status=status,
        source=source,
        evidence=evidence or {},
    )
    session.add(record)

    current = await session.execute(
        select(ConsentCurrent).where(ConsentCurrent.contact_id == contact_id, ConsentCurrent.channel == channel)
    )
    row = current.scalar_one_or_none()
    if row:
        row.status = status
    else:
        session.add(ConsentCurrent(contact_id=contact_id, channel=channel, status=status))

    await session.flush()
    return record


async def get_primary_contact_id(session: AsyncSession, lead_id: uuid.UUID) -> Optional[uuid.UUID]:
    result = await session.execute(
        select(Contact.id)
        .where(Contact.lead_id == lead_id, Contact.deleted_at.is_(None))
        .order_by(Contact.is_primary.desc(), Contact.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_contact_id_by_email(session: AsyncSession, account_id: uuid.UUID, email: str) -> Optional[uuid.UUID]:
    """Used by the SendGrid unsubscribe webhook, which only gives us an email
    address — not a lead_id — to attribute the opt-out to."""
    result = await session.execute(
        select(Contact.id).where(Contact.account_id == account_id, Contact.email == email, Contact.deleted_at.is_(None))
    )
    return result.scalars().first()


async def get_lead_id_by_contact(session: AsyncSession, contact_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Reverse of get_primary_contact_id — used by webhook status-update
    handlers, which only have `email_sends.contact_id`/`whatsapp_sends.contact_id`
    on hand, to attribute the resulting outreach_event back to a lead (needed
    for scoring engagement — see repositories/lead_repo.py::_gather_signals)."""
    result = await session.execute(select(Contact.lead_id).where(Contact.id == contact_id))
    return result.scalar_one_or_none()
