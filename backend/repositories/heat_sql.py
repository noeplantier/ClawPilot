"""SQL twin of services/outreach_os/heat.py, for ordering and tier counts. Integer arithmetic on both sides."""

from __future__ import annotations

from sqlalchemy import Integer, String, Subquery, and_, case, func, literal, select
from sqlalchemy.sql.elements import ColumnElement

from db.models import Lead, ProspectScore
from services.outreach_os import heat as heat_rules

_COLUMNS = {
    "email": Lead.email,
    "phone": Lead.phone,
    "website": Lead.website,
    "city": Lead.city,
    "company": Lead.company,
    "vertical": Lead.vertical,
    "country": Lead.country,
    "title": Lead.title,
}


def _known(column: ColumnElement) -> ColumnElement:
    text_value = func.lower(func.btrim(func.coalesce(column.cast(String), "")))
    return case((text_value.in_(sorted(heat_rules.NOT_KNOWN)), 0), else_=1)


def known(column: ColumnElement) -> ColumnElement:
    """1 when the column really holds a value, 0 for blank / unknown / "unspecified" (the Python `is_known`)."""
    return _known(column)


def has_contact_sql() -> ColumnElement:
    """True when at least one of e-mail, phone, website is really known (the Python `heat.has_contact`)."""
    return sum((_known(_COLUMNS[f]) for f in heat_rules.CONTACT_FIELDS), literal(0)) > 0


def info_pct_sql() -> ColumnElement:
    count = sum((_known(_COLUMNS[f]) for f in heat_rules.INFO_FIELDS), literal(0))
    return (count * 25 + 1) // 2


def heat_sql(score: ColumnElement) -> ColumnElement:
    """`score` is NULL for a lead that was never scored (then the heat is the information alone)."""
    info = info_pct_sql()
    return case((score.is_(None), info), else_=(score.cast(Integer) + info + 1) // 2)


def tier_sql(heat: ColumnElement) -> ColumnElement:
    return case((heat >= heat_rules.HOT_FROM, "hot"), (heat >= heat_rules.WARM_FROM, "warm"), else_="cold")


def top_sql(heat: ColumnElement) -> ColumnElement:
    return heat >= heat_rules.TOP_FROM


def map_ready_sql(score: ColumnElement) -> ColumnElement:
    """True for a hot lead with a phone and an e-mail really known (the Python `heat.is_map_ready`)."""
    return and_(heat_sql(score) >= heat_rules.HOT_FROM, known(Lead.phone) == 1, known(Lead.email) == 1)


def latest_scores() -> Subquery:
    """Each prospect's latest explainable score: the figure a discovery prospect is ranked on."""
    return (
        select(
            ProspectScore.lead_id.label("lead_id"),
            ProspectScore.score.label("score"),
            ProspectScore.coverage.label("coverage"),
            ProspectScore.score_version_id.label("score_version_id"),
        )
        .distinct(ProspectScore.lead_id)
        .order_by(ProspectScore.lead_id, ProspectScore.created_at.desc(), ProspectScore.id)
        .subquery()
    )


def ranked_score(latest: Subquery) -> ColumnElement:
    """The score a lead is ranked on: a prospect's latest score, else a CRM lead's own (0 there means not scored)."""
    return func.coalesce(latest.c.score, func.nullif(Lead.score, 0))
