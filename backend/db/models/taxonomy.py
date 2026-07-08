"""Dynamic targeting segments + tags-as-entities (color, many-to-many with leads)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, CreatedAtMixin, SoftDeleteMixin, TimestampMixin, UUIDPKMixin


class Segment(Base, UUIDPKMixin, TimestampMixin, SoftDeleteMixin):
    """`definition` holds declarative targeting rules, e.g.
    {"stage": "qualified", "score_gte": 50, "inactive_days_gte": 30}.
    Dynamic segments are evaluated on read (no materialization) until a real
    perf need appears — see plan doc section 1.15."""

    __tablename__ = "segments"
    __table_args__ = (
        Index(
            "uq_segments_account_name",
            "account_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    is_dynamic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Tag(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "tags"
    __table_args__ = (Index("uq_tags_account_name", "account_id", "name", unique=True),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str | None] = mapped_column(String, nullable=True)


class LeadTag(Base):
    __tablename__ = "lead_tags"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
