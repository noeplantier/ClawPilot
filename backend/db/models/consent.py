"""Compliance: append-only consent ledger + denormalized current-status lookup.

`ConsentRecord` is the legal evidence trail (never updated/deleted). `ConsentCurrent`
is maintained by the same application transaction that inserts a `ConsentRecord`
(not a DB trigger, so the upsert logic stays testable in Python) and is what every
send task must check before dispatching — see services layer, not this module.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, CreatedAtMixin, UUIDPKMixin

CONSENT_CHANNELS = ("email", "whatsapp")
CONSENT_STATUSES = ("opted_in", "opted_out", "unknown")


class ConsentRecord(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "consent_records"
    __table_args__ = (
        CheckConstraint("channel IN ('email','whatsapp')", name="channel"),
        CheckConstraint("status IN ('opted_in','opted_out','unknown')", name="status"),
        Index("ix_consent_records_contact_channel", "contact_id", "channel", text("recorded_at DESC")),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)


class ConsentCurrent(Base):
    """One row per (contact, channel) — the hot-path read for every send task."""

    __tablename__ = "consent_current"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True
    )
    channel: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"), nullable=False
    )
