"""outbound_messages.status: add 'sending' (the at-most-once marker written before a real send)

Revision ID: a7c1e9d3b5f2
Revises: 487fe7f1b98f
Create Date: 2026-10-02 09:00:00.000000

Alembic does not detect CHECK constraint changes: written by hand. The names are the short ones ("status"); the naming
convention adds the ck_outbound_messages_ prefix, and op.f() passes an already-final name when dropping.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c1e9d3b5f2'
down_revision: Union[str, Sequence[str], None] = '487fe7f1b98f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(op.f('ck_outbound_messages_status'), 'outbound_messages', type_='check')
    op.create_check_constraint(
        'status', 'outbound_messages', "status IN ('sending','sent','failed','bounced','replied')"
    )


def downgrade() -> None:
    # The old constraint has no 'sending': such rows (outcome unknown) become 'failed' — check the mailbox's Sent folder.
    op.execute("UPDATE outbound_messages SET status = 'failed' WHERE status = 'sending'")
    op.drop_constraint(op.f('ck_outbound_messages_status'), 'outbound_messages', type_='check')
    op.create_check_constraint('status', 'outbound_messages', "status IN ('sent','failed','bounced','replied')")
