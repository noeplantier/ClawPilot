"""Persisted map discovery and free enrichment queue.

Revision ID: 20261024_01
Revises: c3bad547cfc1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261024_01"
down_revision = "c3bad547cfc1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("website", sa.Text()),
        sa.Column("phone", sa.String(100)),
        sa.Column("address", sa.Text()),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "source_key", name="uq_companies_account_source"),
    )
    op.create_index("ix_companies_account_name", "companies", ["account_id", "name"])
    op.add_column("leads", sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_leads_company_id_companies",
        "leads",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_leads_company_id", "leads", ["company_id"])
    op.create_table(
        "discovery_jobs",
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("bbox", postgresql.JSONB(), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("result_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "cache_key", name="uq_discovery_jobs_account_cache"),
    )
    op.create_index(
        "ix_discovery_jobs_account_status_created",
        "discovery_jobs",
        ["account_id", "status", "created_at"],
    )
    op.create_table(
        "discovered_places",
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("discovery_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("address", sa.Text()),
        sa.Column("website", sa.Text()),
        sa.Column("phone", sa.String(100)),
        sa.Column("tags", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="SET NULL")),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "source_key", name="uq_discovered_places_account_source"),
    )
    op.create_index("ix_discovered_places_account_job", "discovered_places", ["account_id", "job_id"])
    op.create_table(
        "enrichment_jobs",
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_enrichment_jobs_account_status_created",
        "enrichment_jobs",
        ["account_id", "status", "created_at"],
    )
    op.create_index(
        "uq_enrichment_jobs_active_lead",
        "enrichment_jobs",
        ["account_id", "lead_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )
    op.create_table(
        "public_page_cache",
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("data", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("source_type", sa.String(40), server_default="public_website", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", name="uq_public_page_cache_url"),
    )


def downgrade() -> None:
    op.drop_table("public_page_cache")
    op.drop_index("uq_enrichment_jobs_active_lead", table_name="enrichment_jobs")
    op.drop_index("ix_enrichment_jobs_account_status_created", table_name="enrichment_jobs")
    op.drop_table("enrichment_jobs")
    op.drop_index("ix_discovered_places_account_job", table_name="discovered_places")
    op.drop_table("discovered_places")
    op.drop_index("ix_discovery_jobs_account_status_created", table_name="discovery_jobs")
    op.drop_table("discovery_jobs")
    op.drop_index("ix_leads_company_id", table_name="leads")
    op.drop_constraint("fk_leads_company_id_companies", "leads", type_="foreignkey")
    op.drop_column("leads", "company_id")
    op.drop_index("ix_companies_account_name", table_name="companies")
    op.drop_table("companies")
