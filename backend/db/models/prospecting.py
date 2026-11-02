"""Persisted public-source discovery and enrichment queue records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPKMixin


class Company(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("account_id", "source_key", name="uq_companies_account_source"),
        Index("ix_companies_account_name", "account_id", "name"),
        Index("ix_companies_qualification_website", "website", postgresql_where=text("website IS NOT NULL")),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)


class DiscoveryJob(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "discovery_jobs"
    __table_args__ = (
        UniqueConstraint("account_id", "cache_key", name="uq_discovery_jobs_account_cache"),
        Index("ix_discovery_jobs_account_status_created", "account_id", "status", "created_at"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    bbox: Mapped[list] = mapped_column(JSONB, nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="queued")
    result_count: Mapped[int] = mapped_column(nullable=False, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DiscoveredPlace(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "discovered_places"
    __table_args__ = (
        UniqueConstraint("account_id", "source_key", name="uq_discovered_places_account_source"),
        Index("ix_discovered_places_account_job", "account_id", "job_id"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )


class EnrichmentJob(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "enrichment_jobs"
    __table_args__ = (
        Index("ix_enrichment_jobs_account_status_created", "account_id", "status", "created_at"),
        Index(
            "uq_enrichment_jobs_active_lead",
            "account_id",
            "lead_id",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="queued")


class PublicPageCache(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "public_page_cache"
    __table_args__ = (UniqueConstraint("url", name="uq_public_page_cache_url"),)

    url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProspectingBatch(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "prospecting_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','discovering','enriching','qualifying','completed','partial','paused','failed','canceled')",
            name="chk_prospecting_batches_status",
        ),
        Index("ix_prospecting_batches_account_status", "account_id", "status", text("created_at DESC")),
        Index(
            "uq_prospecting_batches_account_idempotency",
            "account_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="queued")
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    counters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    exclusion_reasons: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ProspectingBatchItem(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "prospecting_batch_items"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('discovered','enriched','qualified_strict','hot','excluded','failed')",
            name="chk_prospecting_batch_items_stage",
        ),
        Index("ix_prospecting_batch_items_batch_stage", "batch_id", "stage"),
        Index("ix_prospecting_batch_items_account_source", "account_id", "source_key"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prospecting_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False, server_default="discovered")
    exclusion_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

