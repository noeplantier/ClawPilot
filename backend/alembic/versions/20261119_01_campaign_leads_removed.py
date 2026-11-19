"""campaign_leads: a recipient removed by the person (kept, never picked again, never sent)

Revision ID: 20261119_01
Revises: 20261113_02
Create Date: 2026-11-19 15:00:00.000000

A removed recipient stays in the selection (so a top-up never picks it again) and is excluded from the audience.
Nullable columns only: existing rows are unchanged (nobody removed).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261119_01"
down_revision: Union[str, Sequence[str], None] = "20261113_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("campaign_leads", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("campaign_leads", sa.Column("removed_by_user_id", sa.UUID(), nullable=True))
    op.add_column("campaign_leads", sa.Column("removed_reason", sa.String(), nullable=True))
    op.create_foreign_key(
        op.f("fk_campaign_leads_removed_by_user_id_users"),
        "campaign_leads",
        "users",
        ["removed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_campaign_leads_removed_by_user_id_users"), "campaign_leads", type_="foreignkey")
    op.drop_column("campaign_leads", "removed_reason")
    op.drop_column("campaign_leads", "removed_by_user_id")
    op.drop_column("campaign_leads", "removed_at")
