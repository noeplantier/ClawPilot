"""add lead qualification scores

Revision ID: 368034440904
Revises: 20261024_01
Create Date: 2026-10-25 00:06:32.603468

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '368034440904'
down_revision: Union[str, Sequence[str], None] = '20261024_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("website_quality", sa.Integer(), nullable=True))
    op.add_column("leads", sa.Column("digital_maturity", sa.Integer(), nullable=True))
    op.add_column("leads", sa.Column("fit_score", sa.Integer(), nullable=True))
    op.add_column("leads", sa.Column("priority", sa.String(length=8), nullable=True))
    op.add_column("leads", sa.Column("qualification_scored_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "website_quality_range", "leads", "website_quality IS NULL OR website_quality BETWEEN 0 AND 100"
    )
    op.create_check_constraint(
        "digital_maturity_range", "leads", "digital_maturity IS NULL OR digital_maturity BETWEEN 0 AND 100"
    )
    op.create_check_constraint("fit_score_range", "leads", "fit_score IS NULL OR fit_score BETWEEN 0 AND 100")
    op.create_check_constraint(
        "qualification_priority", "leads", "priority IS NULL OR priority IN ('low','medium','high')"
    )
    op.create_check_constraint(
        "qualification_scores_complete",
        "leads",
        "(website_quality IS NULL AND digital_maturity IS NULL AND fit_score IS NULL AND priority IS NULL) "
        "OR (website_quality IS NOT NULL AND digital_maturity IS NOT NULL AND fit_score IS NOT NULL AND priority IS NOT NULL)",
    )
    op.create_index(
        "ix_leads_account_qual_priority",
        "leads",
        ["account_id", "priority", sa.text("fit_score DESC")],
        postgresql_where=sa.text("deleted_at IS NULL AND fit_score IS NOT NULL"),
    )
    op.create_index(
        "ix_leads_qualification_website_scan",
        "leads",
        ["website"],
        postgresql_where=sa.text("deleted_at IS NULL AND website IS NOT NULL"),
    )
    op.create_index(
        "ix_companies_qualification_website",
        "companies",
        ["website"],
        postgresql_where=sa.text("website IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_companies_qualification_website", table_name="companies")
    op.drop_index("ix_leads_qualification_website_scan", table_name="leads")
    op.drop_index("ix_leads_account_qual_priority", table_name="leads")
    op.drop_constraint(op.f("ck_leads_qualification_scores_complete"), "leads", type_="check")
    op.drop_constraint(op.f("ck_leads_qualification_priority"), "leads", type_="check")
    op.drop_constraint(op.f("ck_leads_fit_score_range"), "leads", type_="check")
    op.drop_constraint(op.f("ck_leads_digital_maturity_range"), "leads", type_="check")
    op.drop_constraint(op.f("ck_leads_website_quality_range"), "leads", type_="check")
    op.drop_column("leads", "qualification_scored_at")
    op.drop_column("leads", "priority")
    op.drop_column("leads", "fit_score")
    op.drop_column("leads", "digital_maturity")
    op.drop_column("leads", "website_quality")
