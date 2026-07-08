"""Outreach timeline (analytics source of truth) + per-channel send detail tables.

`OutreachEvent` is the unified append-only timeline that real analytics timeseries
are built from (replacing the synthetic random data in the legacy analytics route).
`EmailSend`/`WhatsappSend` hold the per-channel execution detail (subject/body/
provider ids) that a generic event row doesn't need. A single logical send produces
one `email_sends`/`whatsapp_sends` row plus N `outreach_events` rows over time
(queued -> sent -> delivered -> opened, one per webhook).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Computed, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPKMixin

OUTREACH_EVENT_TYPES = (
    "queued",
    "sent",
    "delivered",
    "opened",
    "clicked",
    "replied",
    "bounced",
    "failed",
    "opted_out",
)
SEND_STATUSES = (
    "queued",
    "sent",
    "delivered",
    "opened",
    "clicked",
    "replied",
    "bounced",
    "failed",
    "mock",
)


class OutreachEvent(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "outreach_events"
    __table_args__ = (
        CheckConstraint("channel IN ('email','whatsapp')", name="channel"),
        CheckConstraint(
            "event_type IN "
            "('queued','sent','delivered','opened','clicked','replied','bounced','failed','opted_out')",
            name="event_type",
        ),
        CheckConstraint("direction IN ('outbound','inbound')", name="direction"),
        Index("ix_outreach_events_account_time", "account_id", text("occurred_at DESC")),
        Index("ix_outreach_events_campaign_type", "campaign_id", "event_type"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    campaign_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign_steps.id", ondelete="SET NULL"), nullable=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False, server_default="outbound")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class EmailSend(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "email_sends"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','sent','delivered','opened','clicked','replied','bounced','failed','mock')",
            name="status",
        ),
        Index("ix_email_sends_provider_id_base", "provider_message_id_base"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    campaign_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign_steps.id", ondelete="SET NULL"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    to_email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="queued")
    provider: Mapped[str] = mapped_column(String, nullable=False, server_default="sendgrid")
    provider_message_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # SendGrid appends a suffix to the message id; webhooks match by prefix (see routes/webhooks.py).
    provider_message_id_base: Mapped[str | None] = mapped_column(
        String, Computed("split_part(provider_message_id, '.', 1)", persisted=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WhatsappSend(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "whatsapp_sends"
    __table_args__ = (
        CheckConstraint("direction IN ('outbound','inbound')", name="direction"),
        CheckConstraint(
            "status IN ('queued','sent','delivered','opened','replied','failed','mock')",
            name="status",
        ),
    )

    # Nullable: an inbound webhook can arrive before the lead/account is resolved
    # (mirrors legacy routes/webhooks.py behaviour where org_id may be None).
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    direction: Mapped[str] = mapped_column(String, nullable=False)
    from_number: Mapped[str] = mapped_column(String, nullable=False, index=True)
    to_number: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="queued")
    provider: Mapped[str] = mapped_column(String, nullable=False, server_default="twilio")
    provider_message_sid: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
