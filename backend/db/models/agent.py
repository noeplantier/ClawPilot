"""Agent — display/config entity; becomes the source of truth for which Celery
periodic job categories are active for a given account (see plan doc, section 1.20).
`tasks_completed`/`tasks_in_queue` are real counters updated by Celery tasks,
replacing the legacy random log simulation in routes/agents.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPKMixin


class Agent(Base, UUIDPKMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("role IN ('outreach','enrichment','scraper','responder')", name="role"),
        CheckConstraint("status IN ('idle','running','paused','error')", name="status"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, server_default="outreach")
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="idle")
    tasks_completed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tasks_in_queue: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_heartbeat: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
