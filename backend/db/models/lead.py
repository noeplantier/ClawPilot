"""Lead (prospect), its source, its scoring history, and its contacts."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, CreatedAtMixin, SoftDeleteMixin, TimestampMixin, UUIDPKMixin

LEAD_STAGES = ("new", "contacted", "engaged", "qualified", "won", "lost")


class LeadSource(Base, UUIDPKMixin, CreatedAtMixin):
    """Traceable lead origin — replaces the free-text `source` string."""

    __tablename__ = "lead_sources"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('manual','csv_import','scraper','api','enrichment','referral')",
            name="kind",
        ),
        Index("uq_lead_sources_account_name", "account_id", "name", unique=True),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False, server_default="manual")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class Lead(Base, UUIDPKMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('new','contacted','engaged','qualified','won','lost')",
            name="stage",
        ),
        Index(
            "uq_leads_account_email",
            "account_id",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND email IS NOT NULL"),
        ),
        Index(
            "ix_leads_account_stage",
            "account_id",
            "stage",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_leads_account_score",
            "account_id",
            text("score DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(
            "review_status IS NULL OR review_status IN ('pending','approved','rejected')",
            name="review_status",
        ),
        Index(
            "ix_leads_account_review",
            "account_id",
            "review_status",
            postgresql_where=text("deleted_at IS NULL AND review_status IS NOT NULL"),
        ),
        Index("ix_leads_match_keys_gin", "match_keys", postgresql_using="gin"),
        Index("ix_leads_tags_gin", "tags", postgresql_using="gin"),
        Index("ix_leads_account_created", "account_id", text("created_at DESC")),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    company: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[str] = mapped_column(String, nullable=False, server_default="en")
    stage: Mapped[str] = mapped_column(String, nullable=False, server_default="new")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default=text("'{}'"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lead_sources.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # --- OutreachOS discovery (NULL review_status = a lead that never went through discovery) ---
    vertical: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    match_keys: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default=text("'{}'"))
    review_status: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    contacts: Mapped[list["Contact"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    score_history: Mapped[list["LeadScore"]] = relationship(back_populates="lead", cascade="all, delete-orphan")


class LeadScore(Base, UUIDPKMixin, CreatedAtMixin):
    """Append-only scoring ledger. `Lead.score` is the denormalized current value,
    updated by whichever service (route or Celery task) inserts a new row here."""

    __tablename__ = "lead_scores"
    __table_args__ = (
        CheckConstraint("computed_by IN ('system','celery_task','manual')", name="computed_by"),
        Index("ix_lead_scores_lead_created", "lead_id", text("created_at DESC")),
    )

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_by: Mapped[str] = mapped_column(String, nullable=False, server_default="system")

    lead: Mapped["Lead"] = relationship(back_populates="score_history")


class Contact(Base, UUIDPKMixin, TimestampMixin, SoftDeleteMixin):
    """A physical person at a lead's company. 1:1 with `Lead` at migration time,
    N:1 supported going forward (multiple decision-makers per target account)."""

    __tablename__ = "contacts"
    __table_args__ = (
        Index(
            "uq_contacts_lead_email",
            "lead_id",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND email IS NOT NULL"),
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    role_title: Mapped[str | None] = mapped_column(String, nullable=True)
    is_primary: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))

    lead: Mapped["Lead"] = relationship(back_populates="contacts")
