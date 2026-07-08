"""Raw inbound webhook log — decouples fast receipt (must ack SendGrid/Twilio quickly)
from idempotent processing (done by a Celery task, retriable on failure)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, UUIDPKMixin


class WebhookEvent(Base, UUIDPKMixin):
    __tablename__ = "webhook_events"
    __table_args__ = (
        CheckConstraint("provider IN ('sendgrid','twilio')", name="provider"),
        Index("ix_webhook_events_unprocessed", "received_at", postgresql_where=text("processed = false")),
    )

    provider: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
