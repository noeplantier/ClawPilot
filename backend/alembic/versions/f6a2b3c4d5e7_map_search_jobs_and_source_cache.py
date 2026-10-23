"""map search jobs, staged results and source cache

Revision ID: f6a2b3c4d5e7
Revises: e5f1a2b3c4d6
Create Date: 2026-10-23 09:21:10.562254

CHECK constraints are named with the short names "status" and "source" (the naming convention adds the table prefix).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f6a2b3c4d5e7'
down_revision: Union[str, Sequence[str], None] = 'e5f1a2b3c4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('source_cache',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_source_cache'))
    )
    op.create_index('ix_source_cache_expires', 'source_cache', ['expires_at'], unique=False)
    op.create_table('map_search_jobs',
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('category', sa.String(), nullable=False),
    sa.Column('south', sa.Float(), nullable=False),
    sa.Column('west', sa.Float(), nullable=False),
    sa.Column('north', sa.Float(), nullable=False),
    sa.Column('east', sa.Float(), nullable=False),
    sa.Column('status', sa.String(), server_default='queued', nullable=False),
    sa.Column('source', sa.String(), server_default='overpass', nullable=False),
    sa.Column('result_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('truncated', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('cache_hit', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('error_code', sa.String(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source IN ('overpass','overpass_browser','cache')", name=op.f('ck_map_search_jobs_source')),
    sa.CheckConstraint("status IN ('queued','running','succeeded','failed')", name=op.f('ck_map_search_jobs_status')),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_map_search_jobs_account_id_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_map_search_jobs_created_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_map_search_jobs'))
    )
    op.create_index('ix_map_search_jobs_account_created', 'map_search_jobs', ['account_id', sa.literal_column('created_at DESC')], unique=False)
    op.create_table('map_search_results',
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('dedupe_key', sa.String(), nullable=False),
    sa.Column('external_id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('category', sa.String(), nullable=True),
    sa.Column('lat', sa.Float(), nullable=False),
    sa.Column('lon', sa.Float(), nullable=False),
    sa.Column('address', sa.String(), nullable=True),
    sa.Column('postcode', sa.String(), nullable=True),
    sa.Column('city', sa.String(), nullable=True),
    sa.Column('phone', sa.String(), nullable=True),
    sa.Column('email', sa.String(), nullable=True),
    sa.Column('website', sa.String(), nullable=True),
    sa.Column('source_type', sa.String(), server_default='openstreetmap', nullable=False),
    sa.Column('source_url', sa.String(), nullable=False),
    sa.Column('collected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_map_search_results_account_id_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['job_id'], ['map_search_jobs.id'], name=op.f('fk_map_search_results_job_id_map_search_jobs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_map_search_results'))
    )
    op.create_index('ix_map_search_results_account_key', 'map_search_results', ['account_id', 'dedupe_key'], unique=False)
    op.create_index('uq_map_search_results_job_key', 'map_search_results', ['job_id', 'dedupe_key'], unique=True)


def downgrade() -> None:
    op.drop_index('uq_map_search_results_job_key', table_name='map_search_results')
    op.drop_index('ix_map_search_results_account_key', table_name='map_search_results')
    op.drop_table('map_search_results')
    op.drop_index('ix_map_search_jobs_account_created', table_name='map_search_jobs')
    op.drop_table('map_search_jobs')
    op.drop_index('ix_source_cache_expires', table_name='source_cache')
    op.drop_table('source_cache')
