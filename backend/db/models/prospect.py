"""OutreachOS discovery data: provenance, signals, score versions/history, message drafts, suppression, usage.

Append-only (never updated, never logically deleted): ProspectSource, ProspectSignal, ScoreVersion,
ProspectScore, UsageRecord. The only sanctioned mutation is the erasure path, which blanks
`ProspectSource.fields` so no personal data survives a deletion request (see docs/compliance.md).
`MessageDraft` is a business table (its status changes on human review).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPKMixin

SIGNAL_STATES = ("unknown", "detected", "not_detected")
DRAFT_STATUSES = ("draft", "approved", "rejected")
SUPPRESSION_KINDS = ("email", "phone", "domain")
SUPPRESSION_REASONS = ("opt_out", "erasure", "bounce", "manual")
USAGE_KINDS = ("discovery_run", "signals_analyzed", "drafts_generated", "messages_dispatched")


def _account_fk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)


def _lead_fk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)


class ProspectSource(Base, UUIDPKMixin, CreatedAtMixin):
    """Where a prospect's data came from: one row per (source listing, content version)."""

    __tablename__ = "prospect_sources"
    __table_args__ = (
        Index(
            "uq_prospect_sources_listing_version",
            "account_id",
            "source_name",
            "external_id",
            "content_hash",
            unique=True,
        ),
        Index("ix_prospect_sources_lead", "lead_id"),
    )

    account_id: Mapped[uuid.UUID] = _account_fk()
    lead_id: Mapped[uuid.UUID] = _lead_fk()
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    license_note: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    fields: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class ProspectSignal(Base, UUIDPKMixin, CreatedAtMixin):
    """One observation of one signal. The current state is the latest row per (lead, signal_key)."""

    __tablename__ = "prospect_signals"
    __table_args__ = (
        CheckConstraint("state IN ('unknown','detected','not_detected')", name="state"),
        Index("ix_prospect_signals_lead_key", "lead_id", "signal_key", text("created_at DESC")),
    )

    account_id: Mapped[uuid.UUID] = _account_fk()
    lead_id: Mapped[uuid.UUID] = _lead_fk()
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospect_sources.id", ondelete="SET NULL"), nullable=True
    )
    signal_key: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)


class ScoreVersion(Base, UUIDPKMixin, CreatedAtMixin):
    """An immutable scoring configuration. Every change adds a version; the highest is active."""

    __tablename__ = "score_versions"
    __table_args__ = (
        Index("uq_score_versions_account_version", "account_id", "version", unique=True),
        Index("ix_score_versions_account_hash", "account_id", "config_hash"),
    )

    account_id: Mapped[uuid.UUID] = _account_fk()
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    config_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ProspectScore(Base, UUIDPKMixin, CreatedAtMixin):
    """Digital-need score history. Distinct from `lead_scores` (profile-fit scoring of the CRM)."""

    __tablename__ = "prospect_scores"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="range"),
        Index("ix_prospect_scores_lead_created", "lead_id", text("created_at DESC")),
    )

    account_id: Mapped[uuid.UUID] = _account_fk()
    lead_id: Mapped[uuid.UUID] = _lead_fk()
    score_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("score_versions.id", ondelete="RESTRICT"), nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage: Mapped[float] = mapped_column(Float, nullable=False)
    breakdown: Mapped[list] = mapped_column(JSONB, nullable=False)


class MessageDraft(Base, UUIDPKMixin, TimestampMixin):
    """A message prepared for a human to approve. Nothing here is ever sent by this slice."""

    __tablename__ = "message_drafts"
    __table_args__ = (
        CheckConstraint("channel IN ('email')", name="channel"),
        CheckConstraint("status IN ('draft','approved','rejected')", name="status"),
        Index("uq_message_drafts_account_idempotency", "account_id", "idempotency_key", unique=True),
        Index("ix_message_drafts_lead_created", "lead_id", text("created_at DESC")),
    )

    account_id: Mapped[uuid.UUID] = _account_fk()
    lead_id: Mapped[uuid.UUID] = _lead_fk()
    campaign_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign_steps.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String, nullable=False, server_default="email")
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    facts: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    template_version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="draft")
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SuppressionEntry(Base, UUIDPKMixin, CreatedAtMixin):
    """Do-not-contact list of one organisation, stored as digests so it holds no clear-text identity.

    Scoped per account on purpose: each organisation is the controller of its own prospect data, so its
    opt-outs and erasures must neither leak to nor be forgeable against another tenant.
    """

    __tablename__ = "suppression_entries"
    __table_args__ = (
        CheckConstraint("kind IN ('email','phone','domain')", name="kind"),
        CheckConstraint("reason IN ('opt_out','erasure','bounce','manual')", name="reason"),
        Index("uq_suppression_entries_identity", "account_id", "kind", "identity_hash", unique=True),
    )

    kind: Mapped[str] = mapped_column(String, nullable=False)
    identity_hash: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    account_id: Mapped[uuid.UUID] = _account_fk()


class UsageRecord(Base, UUIDPKMixin, CreatedAtMixin):
    """Metering ledger for cost control: what a run consumed, per account."""

    __tablename__ = "usage_records"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('discovery_run','signals_analyzed','drafts_generated','messages_dispatched')", name="kind"
        ),
        CheckConstraint("quantity >= 0", name="quantity"),
        Index("ix_usage_records_account_created", "account_id", text("created_at DESC")),
    )

    account_id: Mapped[uuid.UUID] = _account_fk()
    kind: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
