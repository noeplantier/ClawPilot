"""Compliance envelope for the legacy e-mail paths (single send, batch, campaign step, Celery task).

Every e-mail sent through SendGrid goes through `prepare()` first: it refuses a suppressed recipient, then appends the
sender identity, the origin of the data and a signed unsubscribe link to the body, and returns the RFC 8058 headers.
Fail closed: with SendGrid configured (a message can really leave), a missing sender identity or a missing recipient
record makes `prepare()` raise `EmailNotCompliant` and nothing is sent. Without SendGrid nothing can leave, so the
message stays untouched (mock) when the identity is not configured.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from deps import JWT_SECRET
from repositories import suppression_repo
from services import sendgrid_svc
from services.outreach_os import channels, email_footer
from services.outreach_os.drafts import SenderIdentity
from services.outreach_os.normalize import normalize_email
from services.outreach_os.unsubscribe import make_token


class EmailNotCompliant(Exception):
    """The message must not leave. `code` is stable; `message` is safe to show."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PreparedEmail:
    body: str
    headers: dict[str, str] = field(default_factory=dict)


def unsubscribe_url(account_id: uuid.UUID, lead_id: uuid.UUID) -> str:
    base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/api/unsubscribe/{make_token(JWT_SECRET, account_id, lead_id)}"


async def prepare(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    to_email: str,
    body: str,
    lead_id: Optional[str] = None,
    source: Optional[str] = None,
) -> PreparedEmail:
    """The body to send (footer included) and its headers, or `EmailNotCompliant`."""
    if await suppression_repo.is_suppressed(session, account_id, email=normalize_email(to_email)):
        raise EmailNotCompliant("suppressed", "Recipient is on the suppression list")
    enforce = sendgrid_svc.is_configured()
    sender = SenderIdentity.from_env()
    if sender is None:
        if enforce:
            raise EmailNotCompliant(
                "sender_not_configured",
                "Sender identity is not configured (OUTREACH_SENDER_NAME, _COMPANY, _ADDRESS, _EMAIL)",
            )
        return PreparedEmail(body)
    try:
        lead_uuid = uuid.UUID(lead_id) if lead_id else None
    except ValueError:
        lead_uuid = None
    if lead_uuid is None:
        if enforce:
            raise EmailNotCompliant(
                "recipient_unknown",
                "lead_id is required: a message without a recipient record cannot carry a working unsubscribe link",
            )
        return PreparedEmail(body)
    url = unsubscribe_url(account_id, lead_uuid)
    footer = email_footer.render_footer(
        name=sender.name,
        company=sender.company,
        postal_address=sender.postal_address,
        source=source,
        unsubscribe_url=url,
    )
    full = email_footer.append_footer(body, footer, url)
    problems = email_footer.footer_problems(
        full, name=sender.name, company=sender.company, postal_address=sender.postal_address, unsubscribe_url=url
    )
    if problems:  # defence in depth: the footer was just appended, this only fires if the rules above drift apart
        raise EmailNotCompliant("not_compliant", f"Message is not compliant: {', '.join(problems)}")
    return PreparedEmail(full, channels.unsubscribe_headers(url))
