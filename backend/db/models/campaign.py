"""Campaign + its steps, assigned leads, and per-channel send policy (throttling/windows)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPKMixin

CAMPAIGN_STATUSES = ("draft", "running", "paused", "completed")
# One planned message of an individual campaign. `scheduled` waits for its time; `sending` is the marker taken just
# before the send ledger is written (a row stuck there is reconciled, never blindly retried); `accepted` = the channel
# adapter took the message (what happened next lives in `outbound_messages`: reply, bounce, opposition); `unknown` = the
# outcome could not be established and is never retried; `skipped` = a gate stopped it (reason in `last_reason`);
# `cancelled` = a person did.
DISPATCH_STATUSES = ("scheduled", "sending", "accepted", "failed", "unknown", "skipped", "cancelled")
CHANNELS = ("email", "whatsapp")


CAMPAIGN_KINDS = ("sequence", "individual")


class Campaign(Base, UUIDPKMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint("status IN ('draft','running','paused','completed')", name="status"),
        CheckConstraint("kind IN ('sequence','individual')", name="kind"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="draft")
    # "sequence" = steps (templates) run by the campaign engine; "individual" = one approved, personalised draft per
    # recipient, planned in campaign_dispatches and sent one by one (no steps, never run by the sequence engine).
    kind: Mapped[str] = mapped_column(String, nullable=False, server_default="sequence")
    # The perimeter of a "zone -> draft -> approval" campaign: {kind: "bbox", south, west, north, east, category,
    # label}.
    # NULL for every other campaign. Only prospects positioned inside it are candidates.
    zone: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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
        CheckConstraint("max_per_day BETWEEN 0 AND 100000", name="max_per_day"),
        CheckConstraint("min_delay_seconds BETWEEN 0 AND 86400", name="min_delay_seconds"),
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
    # --- OutreachOS dispatch limits (conservative defaults) and the per-account kill switch ---
    max_per_day: Mapped[int] = mapped_column(Integer, nullable=False, server_default="20")
    min_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    sending_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class CampaignDispatch(Base, UUIDPKMixin, TimestampMixin):
    """The plan of one message: one prepared, approved draft for one recipient, at the earliest time it may leave.

    Created by "Planifier les messages approuvés"; consumed by the scheduled task that sends each one through the same
    dispatch as every other path (services/campaign_launch.py). Nothing is sent by writing this row."""

    __tablename__ = "campaign_dispatches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled','sending','accepted','failed','unknown','skipped','cancelled')", name="status"
        ),
        Index("uq_campaign_dispatches_campaign_lead", "campaign_id", "lead_id", unique=True),
        # a prospect has at most one message planned or in flight, whatever the campaign
        Index(
            "uq_campaign_dispatches_active_lead",
            "account_id",
            "lead_id",
            unique=True,
            postgresql_where=text("status IN ('scheduled','sending')"),
        ),
        Index("ix_campaign_dispatches_due", "status", "planned_at"),
        Index("ix_campaign_dispatches_account_campaign", "account_id", "campaign_id", "status"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("message_drafts.id", ondelete="SET NULL"), nullable=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outbound_messages.id", ondelete="SET NULL"), nullable=True
    )
    # the address at planning time: a change of address stops the send
    to_email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="scheduled")
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
