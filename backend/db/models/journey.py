"""The journey "zone -> draft -> approval" and the bounded automation mandate.

* `campaign_templates`: the controlled message template of a campaign, one row per version (append-only: an edit is
  a new version, the earlier ones stay as they were approved).
* `campaign_approvals`: what a person (or, inside a mandate, the mandate) approved: a version of the template, a
  zone, an offer, a sender, a volume. Anything that changes one of them makes the approval stale (services/outreach_os/
  campaign_template.py); revoking one stops the messages that have not left.
* `automation_mandates` + `mandate_events`: ONE explicit, bounded authorisation for "Automatisation max" (zones,
  template version, sender, caps, expiry, stop rules) and its append-only journal. Off by default: no row, no
  automation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPKMixin

MANDATE_STATUSES = ("draft", "active", "suspended", "revoked", "expired")


def _account() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)


class CampaignTemplate(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "campaign_templates"
    __table_args__ = (Index("uq_campaign_templates_campaign_version", "campaign_id", "version", unique=True),)

    account_id: Mapped[uuid.UUID] = _account()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    offer_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class CampaignApproval(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "campaign_approvals"
    __table_args__ = (Index("ix_campaign_approvals_campaign", "campaign_id", "created_at"),)

    account_id: Mapped[uuid.UUID] = _account()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    zone_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    offer_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sender_fp: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    audience_count: Mapped[int] = mapped_column(Integer, nullable=False)  # what the person was shown
    daily_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    mandate_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_mandates.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoke_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class AutomationMandate(Base, UUIDPKMixin, TimestampMixin):
    """One explicit, bounded authorisation for the automatic mode. Nothing automatic happens without an `active` one,
    and nothing outside it: not another zone, another template version, another sender, more than its caps, after it."""

    __tablename__ = "automation_mandates"
    __table_args__ = (
        CheckConstraint("status IN ('draft','active','suspended','revoked','expired')", name="status"),
        CheckConstraint("daily_cap BETWEEN 1 AND 1000 AND total_cap BETWEEN 1 AND 100000", name="caps"),
        Index("ix_automation_mandates_account_status", "account_id", "status"),
    )

    account_id: Mapped[uuid.UUID] = _account()
    campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="draft")
    zones: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    zone_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    offer_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    sender_fp: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    daily_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_budget: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )  # AI generations allowed: 0 = none
    window_start_hour: Mapped[int] = mapped_column(Integer, nullable=False, server_default="8")
    window_end_hour: Mapped[int] = mapped_column(Integer, nullable=False, server_default="18")
    min_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    search_every_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default="24")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stop_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    activated_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_search_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # revoked / expired / suspended: why


class MandateEvent(Base, UUIDPKMixin, CreatedAtMixin):
    """The journal of a mandate, append-only: every authorisation, change, run, stop and refusal."""

    __tablename__ = "mandate_events"
    __table_args__ = (Index("ix_mandate_events_mandate_created", "mandate_id", "created_at"),)

    account_id: Mapped[uuid.UUID] = _account()
    mandate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_mandates.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    actor_type: Mapped[str] = mapped_column(String, nullable=False, server_default="system")
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
