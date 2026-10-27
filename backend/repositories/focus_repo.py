"""What to work on next: the hottest leads that can be both called and e-mailed. SQL reads only, via heat_sql."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Lead
from repositories import heat_sql, suppression_repo
from services.outreach_os import heat as heat_rules
from services.outreach_os.normalize import normalize_domain, normalize_email, normalize_phone


async def best_leads(session: AsyncSession, account_id: uuid.UUID, limit: int = 8) -> list[dict]:
    """Hot leads with a phone and an e-mail, a website first, then the hottest. A rejected prospect is not a lead and a
    suppressed identity is never suggested; candidates are over-fetched so that filter cannot leave a short list."""
    latest = heat_sql.latest_scores()
    score = heat_sql.ranked_score(latest)
    heat = heat_sql.heat_sql(score)
    rows = await session.execute(
        select(Lead, heat.label("heat"))
        .outerjoin(latest, latest.c.lead_id == Lead.id)
        .where(
            Lead.account_id == account_id,
            Lead.deleted_at.is_(None),
            or_(Lead.review_status.is_(None), Lead.review_status != "rejected"),
            heat_sql.map_ready_sql(score),
        )
        .order_by(heat_sql.known(Lead.website).desc(), heat.desc(), Lead.created_at.desc(), Lead.id)
        .limit(limit * 5)
    )
    out: list[dict] = []
    for lead, value in rows.all():
        if await suppression_repo.is_suppressed(
            session,
            account_id,
            email=normalize_email(lead.email),
            phone=normalize_phone(lead.phone),
            domain=normalize_domain(lead.website),
        ):
            continue
        known = heat_rules.known_fields({f: getattr(lead, f) for f in heat_rules.INFO_FIELDS})
        out.append(
            {
                "id": str(lead.id),
                "name": lead.full_name,
                "company": lead.company if heat_rules.is_known(lead.company) else None,
                "city": lead.city if heat_rules.is_known(lead.city) else None,
                "kind": "prospect" if lead.review_status is not None else "lead",
                "review_status": lead.review_status,
                "heat": {"value": int(value), "tier": "hot", "info_pct": heat_rules.info_pct(len(known))},
                "phone": lead.phone,
                "email": lead.email,
                "website": lead.website if heat_rules.is_known(lead.website) else None,
            }
        )
        if len(out) == limit:
            break
    return out
