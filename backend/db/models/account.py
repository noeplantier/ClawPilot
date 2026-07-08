"""Account (formerly `organizations`) and User."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin, UUIDPKMixin


class Account(Base, UUIDPKMixin, TimestampMixin):
    """No soft-delete: account deletion is a dedicated right-to-be-forgotten
    procedure, not a flag flip (see plan doc, section 1.1)."""

    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("plan IN ('free','pro','enterprise')", name="plan"),)

    name: Mapped[str] = mapped_column(String, nullable=False)
    plan: Mapped[str] = mapped_column(String, nullable=False, server_default="pro")

    users: Mapped[list["User"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class User(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('owner','admin','member')", name="role"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, server_default="owner")

    account: Mapped["Account"] = relationship(back_populates="users")
