"""bounded prospecting mandates: one authorisation per account, draft by default

Revision ID: 20261123_01
Revises: 20261105_01
Create Date: 2026-11-23 10:00:00.000000

The mandate is a decision record, not a campaign: creating it starts nothing. Only an explicit activation may set
`status = 'active'`, and a partial unique index allows at most one active mandate per account. RLS is enabled like
every other public table (the backend connects as the table owner and bypasses it).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261123_01"
down_revision: Union[str, Sequence[str], None] = "20261119_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mandates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("zone", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sector", sa.String(120), nullable=False),
        sa.Column("offer", sa.Text(), nullable=False),
        sa.Column(
            "qualification_criteria",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("daily_volume", sa.Integer(), nullable=False),
        sa.Column("total_volume", sa.Integer(), nullable=False),
        sa.Column("ai_budget", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "time_windows",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("cadence_minutes", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "stop_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('draft','active','paused','expired','revoked')",
            name="chk_mandates_status",
        ),
        sa.CheckConstraint("daily_volume > 0 AND total_volume > 0", name="chk_mandates_volumes"),
        sa.CheckConstraint("ai_budget >= 0", name="chk_mandates_budget"),
        sa.CheckConstraint("cadence_minutes > 0", name="chk_mandates_cadence"),
    )
    op.create_index("ix_mandates_account_status", "mandates", ["account_id", "status"])
    op.create_index(
        "uq_mandates_one_active_per_account",
        "mandates",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.execute("ALTER TABLE mandates ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("mandates")
