"""Dispatch ledger for outbound messages and their lifecycle events.

Kept apart from `email_sends`/`outreach_events` on purpose: those feed the real analytics, and a dry-run
dispatch must never show up as a delivered message in a KPI.
`OutboundEvent` is append-only (erasure blanks `detail`, see docs/compliance.md); `OutboundMessage.status`
advances with bounces and replies. `sending` is the marker committed *before* a real adapter is called: a row that
stays there has an unknown outcome and is never retried by the system (at most once).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPKMixin

OUTBOUND_STATUSES = ("sent", "failed", "bounced", "replied")
OUTBOUND_EVENT_TYPES = ("sent", "failed", "bounced", "replied", "opted_out")


class OutboundMessage(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "outbound_messages"
    __table_args__ = (
        CheckConstraint("channel IN ('email')", name="channel"),
        CheckConstraint("status IN ('sending','sent','failed','bounced','replied')", name="status"),
        Index("uq_outbound_messages_account_idempotency", "account_id", "idempotency_key", unique=True),
        Index("ix_outbound_messages_account_dispatched", "account_id", text("dispatched_at DESC")),
        Index("ix_outbound_messages_lead", "lead_id"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("message_drafts.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String, nullable=False, server_default="email")
    to_email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    adapter: Mapped[str] = mapped_column(String, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status: Mapped[str] = mapped_column(String, nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    dispatched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class OutboundEvent(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "outbound_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('sent','failed','bounced','replied','opted_out')", name="event_type"),
        Index("ix_outbound_events_message_created", "message_id", "created_at"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outbound_messages.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    # clock_timestamp(), not now(): several events can be written in one transaction and must keep their order.
    created_at: Mapped[datetime] = mapped_column(  # type: ignore[assignment]
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
