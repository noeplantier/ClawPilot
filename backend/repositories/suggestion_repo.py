"""Reads the organisation's real leads and prospects as `Candidate`s for the campaign suggestions. Read-only."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Lead
from repositories import lead_repo, prospect_repo
from services.outreach_os import heat as heat_rules
from services.outreach_os.suggestions import Candidate

MAX_CANDIDATES = 5000


async def load_candidates(session: AsyncSession, account_id: uuid.UUID) -> list[Candidate]:
    latest = prospect_repo._latest_scores_subquery()
    rows = await session.execute(
        select(Lead, latest.c.score, lead_repo.sendable_clause().label("sendable"))
        .outerjoin(latest, latest.c.lead_id == Lead.id)
        .where(Lead.account_id == account_id, prospect_repo.ACTIVE)
        .order_by(Lead.created_at.desc(), Lead.id)
        .limit(MAX_CANDIDATES)
    )
    detected = await prospect_repo.detected_by_lead(session, account_id)
    out: list[Candidate] = []
    for lead, prospect_score, sendable in rows.all():
        is_prospect = lead.review_status is not None
        score = prospect_score if is_prospect else (lead.score if lead.score > 0 else None)
        h = heat_rules.heat_of({f: getattr(lead, f) for f in heat_rules.INFO_FIELDS}, score)
        out.append(
            Candidate(
                id=str(lead.id),
                name=lead.company or lead.full_name,
                is_prospect=is_prospect,
                review_status=lead.review_status,
                vertical=lead.vertical if heat_rules.is_known(lead.vertical) else None,
                city=lead.city if heat_rules.is_known(lead.city) else None,
                stage=lead.stage,
                heat=h.value,
                tier=h.tier,
                has_email=heat_rules.is_known(lead.email),
                has_phone=heat_rules.is_known(lead.phone),
                signals=frozenset(detected.get(lead.id, [])),
                sendable_now=bool(sendable),
            )
        )
    return out
