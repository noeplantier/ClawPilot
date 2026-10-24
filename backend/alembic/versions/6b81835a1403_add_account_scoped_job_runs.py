"""add account scoped job runs

Revision ID: 6b81835a1403
Revises: 368034440904
Create Date: 2026-10-25 00:51:53.810677

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b81835a1403'
down_revision: Union[str, Sequence[str], None] = '368034440904'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("processed_items", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_items", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("status IN ('queued','running','succeeded','partial','failed')", name="status"),
        sa.CheckConstraint("total_items >= 0 AND processed_items >= 0 AND failed_items >= 0", name="counts_nonnegative"),
        sa.CheckConstraint("processed_items + failed_items <= total_items", name="counts_within_total"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_runs_account_status_created",
        "job_runs",
        ["account_id", "status", sa.text("created_at DESC")],
    )
    op.create_index("ix_job_runs_account_created", "job_runs", ["account_id", sa.text("created_at DESC")])
    # The application uses the database owner connection and applies account_id filters itself.
    # Keep the Supabase Data API closed, matching the existing public-schema policy.
    op.execute("ALTER TABLE job_runs ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_job_runs_account_created", table_name="job_runs")
    op.drop_index("ix_job_runs_account_status_created", table_name="job_runs")
    op.drop_table("job_runs")
