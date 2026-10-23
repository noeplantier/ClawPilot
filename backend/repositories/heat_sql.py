"""SQL twin of services/outreach_os/heat.py, for ordering and tier counts. Integer arithmetic on both sides."""

from __future__ import annotations

from sqlalchemy import Integer, String, case, func, literal
from sqlalchemy.sql.elements import ColumnElement

from db.models import Lead
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


def info_pct_sql() -> ColumnElement:
    count = sum((_known(_COLUMNS[f]) for f in heat_rules.INFO_FIELDS), literal(0))
    return (count * 25 + 1) // 2


def heat_sql(score: ColumnElement) -> ColumnElement:
    """`score` is NULL for a lead that was never scored (then the heat is the information alone)."""
    info = info_pct_sql()
    return case((score.is_(None), info), else_=(score.cast(Integer) + info + 1) // 2)


def tier_sql(heat: ColumnElement) -> ColumnElement:
    return case((heat >= heat_rules.HOT_FROM, "hot"), (heat >= heat_rules.WARM_FROM, "warm"), else_="cold")
