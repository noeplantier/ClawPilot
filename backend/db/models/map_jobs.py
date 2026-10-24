"""Map search jobs: one row per search, its staged results, and the shared source cache.

`map_search_results` is a staging area, NOT the prospect table: a place becomes a prospect only through the attested
import (origin, legal basis, suppression list, audit). Staged rows expire with their job (30 days, see map_job_repo).
`source_cache` holds parsed public data keyed by (query version, snapped area, category) with a TTL.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, CreatedAtMixin, UUIDPKMixin


class MapSearchJob(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "map_search_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','succeeded','failed')", name="status"),
        CheckConstraint("source IN ('overpass','overpass_browser','cache')", name="source"),
        Index("ix_map_search_jobs_account_created", "account_id", text("created_at DESC")),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[str] = mapped_column(String, nullable=False)
    south: Mapped[float] = mapped_column(Float, nullable=False)
    west: Mapped[float] = mapped_column(Float, nullable=False)
    north: Mapped[float] = mapped_column(Float, nullable=False)
    east: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="queued")
    source: Mapped[str] = mapped_column(String, nullable=False, server_default="overpass")
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    truncated: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    cache_hit: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MapSearchResult(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "map_search_results"
    __table_args__ = (
        Index("uq_map_search_results_job_key", "job_id", "dedupe_key", unique=True),
        Index("ix_map_search_results_account_key", "account_id", "dedupe_key"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("map_search_jobs.id", ondelete="CASCADE"), nullable=False
    )
    dedupe_key: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    postcode: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False, server_default="openstreetmap")
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class SourceCache(Base):
    __tablename__ = "source_cache"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_source_cache_expires", "expires_at"),)
