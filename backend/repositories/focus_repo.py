"""What to work on next: the hottest leads that can be both called and e-mailed. SQL reads only, via heat_sql."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Lead
from repositories import eligibility_sql, heat_sql, suppression_repo
from services.outreach_os import heat as heat_rules
from services.outreach_os.normalize import normalize_domain, normalize_email, normalize_phone


async def best_leads(
    session: AsyncSession, account_id: uuid.UUID, limit: int = 8, now: Optional[datetime] = None
) -> list[dict]:
    """The qualified prospects to work first (common eligibility policy: e-mail, phone, address, fresh source, fit),
    hot ones (observed, sourced intent) before the others, then the hottest by heat. A website only breaks a tie.
    A rejected prospect is not a lead and a suppressed identity is never suggested; candidates are over-fetched so
    that filter cannot leave a short list."""
    latest = heat_sql.latest_scores()
    src = eligibility_sql.latest_source(account_id)
    score = heat_sql.ranked_score(latest)
    heat = heat_sql.heat_sql(score)
    is_hot = eligibility_sql.hot(src, now)
    rows = await session.execute(
        select(Lead, heat.label("heat"), is_hot.label("is_hot"))
        .outerjoin(latest, latest.c.lead_id == Lead.id)
        .join(src, src.c.lead_id == Lead.id)
        .where(Lead.account_id == account_id, Lead.deleted_at.is_(None), eligibility_sql.qualified(src, now))
        .order_by(is_hot.desc(), heat.desc(), heat_sql.known(Lead.website).desc(), Lead.created_at.desc(), Lead.id)
        .limit(limit * 5)
    )
    out: list[dict] = []
    for lead, value, hot_flag in rows.all():
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
                "heat": {
                    "value": int(value),
                    "tier": heat_rules.tier_of(int(value)),
                    "info_pct": heat_rules.info_pct(len(known)),
                },
                "priority": "hot" if hot_flag else "qualified",
                "phone": lead.phone,
                "email": lead.email,
                "website": lead.website if heat_rules.is_known(lead.website) else None,
            }
        )
        if len(out) == limit:
            break
    return out
