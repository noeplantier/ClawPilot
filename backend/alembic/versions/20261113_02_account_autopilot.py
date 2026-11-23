"""account autopilot

Revision ID: 20261113_02
Revises: 20261113_01
Create Date: 2026-11-13 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20261113_02"
down_revision: Union[str, Sequence[str], None] = "20261113_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("autopilot", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "autopilot")
