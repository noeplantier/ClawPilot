"""signal dismissals (a reviewer marks an observed signal as wrong; append-only)

Revision ID: e5f1a2b3c4d6
Revises: c303c1bc427f
Create Date: 2026-10-03 15:00:00.000000

The CHECK constraint is written by hand (Alembic does not detect CHECK changes) with the short name "action": the naming
convention adds the `ck_signal_dismissals_` prefix.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f1a2b3c4d6"
down_revision: Union[str, Sequence[str], None] = "c303c1bc427f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signal_dismissals",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("signal_key", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("action IN ('dismiss','restore')", name=op.f("ck_signal_dismissals_action")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_signal_dismissals_account_id_accounts"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], name=op.f("fk_signal_dismissals_lead_id_leads"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name=op.f("fk_signal_dismissals_actor_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal_dismissals")),
    )
    op.create_index(
        "ix_signal_dismissals_lead_key", "signal_dismissals", ["lead_id", "signal_key", sa.text("created_at DESC")]
    )


def downgrade() -> None:
    op.drop_index("ix_signal_dismissals_lead_key", table_name="signal_dismissals")
    op.drop_table("signal_dismissals")
