"""credits and outreach model

Revision ID: 20261113_01
Revises: 20261111_01
Create Date: 2026-11-13 01:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261113_01"
down_revision: Union[str, Sequence[str], None] = "20261111_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("outreach_model", sa.String(length=32), nullable=True))
    # CHECK constraints are not detected by Alembic: written by hand, with the short name (the convention adds ck_<table>_).
    op.drop_constraint(op.f("ck_usage_records_kind"), "usage_records", type_="check")
    op.create_check_constraint(
        "kind",
        "usage_records",
        "kind IN ('discovery_run','signals_analyzed','drafts_generated','messages_dispatched','credits')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_usage_records_kind"), "usage_records", type_="check")
    op.execute("DELETE FROM usage_records WHERE kind = 'credits'")  # would violate the old CHECK
    op.create_check_constraint(
        "kind", "usage_records", "kind IN ('discovery_run','signals_analyzed','drafts_generated','messages_dispatched')"
    )
    op.drop_column("accounts", "outreach_model")
