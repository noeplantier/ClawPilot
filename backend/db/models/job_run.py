"""Persisted progress for account-scoped background jobs."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, UUIDPKMixin


class JobRun(Base, UUIDPKMixin):
    __tablename__ = "job_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','succeeded','partial','failed')", name="status"),
        CheckConstraint("total_items >= 0 AND processed_items >= 0 AND failed_items >= 0", name="counts_nonnegative"),
        CheckConstraint("processed_items + failed_items <= total_items", name="counts_within_total"),
        Index("ix_job_runs_account_status_created", "account_id", "status", text("created_at DESC")),
        Index("ix_job_runs_account_created", "account_id", text("created_at DESC")),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="queued")
    total_items: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
