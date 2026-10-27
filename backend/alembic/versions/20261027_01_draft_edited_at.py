"""message_drafts.edited_at: a human changed the text of a draft after it was prepared

Revision ID: 20261027_01
Revises: 6b81835a1403
Create Date: 2026-10-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261027_01"
down_revision: Union[str, Sequence[str], None] = "6b81835a1403"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("message_drafts", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("message_drafts", "edited_at")
