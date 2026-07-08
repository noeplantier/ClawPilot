"""Campaign + its steps, assigned leads, and per-channel send policy (throttling/windows)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPKMixin

CAMPAIGN_STATUSES = ("draft", "running", "paused", "completed")
CHANNELS = ("email", "whatsapp")


class Campaign(Base, UUIDPKMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "campaigns"
    __table_args__ = (CheckConstraint("status IN ('draft','running','paused','completed')", name="status"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="draft")
    channels: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default=text("'{email}'"))
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    sent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    opened: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    replied: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    converted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    steps: Mapped[list["CampaignStep"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", order_by="CampaignStep.step_index"
    )
    leads: Mapped[list["CampaignLead"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class CampaignStep(Base, UUIDPKMixin, TimestampMixin):
    """Replaces the JSON-embedded `Campaign.steps` list."""

    __tablename__ = "campaign_steps"
    __table_args__ = (
        CheckConstraint("channel IN ('email','whatsapp')", name="channel"),
        Index("uq_campaign_steps_campaign_index", "campaign_id", "step_index", unique=True),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(String, nullable=False, server_default="email")
    delay_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    language: Mapped[str] = mapped_column(String, nullable=False, server_default="en")

    campaign: Mapped["Campaign"] = relationship(back_populates="steps")


class CampaignLead(Base):
    """Replaces the JSON-embedded `Campaign.lead_ids` list."""

    __tablename__ = "campaign_leads"
    __table_args__ = (Index("ix_campaign_leads_lead", "lead_id"),)

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    campaign: Mapped["Campaign"] = relationship(back_populates="leads")


class SendPolicy(Base, UUIDPKMixin, TimestampMixin):
    """Per-account, per-channel throttle + send-window configuration."""

    __tablename__ = "send_policies"
    __table_args__ = (
        CheckConstraint("channel IN ('email','whatsapp')", name="channel"),
        CheckConstraint(
            "timezone_source IN ('lead_country','account_default')",
            name="tz_source",
        ),
        Index("uq_send_policies_account_channel", "account_id", "channel", unique=True),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String, nullable=False)
    max_per_hour: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    window_start_hour: Mapped[int] = mapped_column(Integer, nullable=False, server_default="8")
    window_end_hour: Mapped[int] = mapped_column(Integer, nullable=False, server_default="18")
    timezone_source: Mapped[str] = mapped_column(String, nullable=False, server_default="lead_country")
    account_default_timezone: Mapped[str] = mapped_column(String, nullable=False, server_default="UTC")
