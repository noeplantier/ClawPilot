"""Dashboard overview: one read-only call that returns real aggregates (and explicit nulls where nothing is known)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from deps import get_current_user
from models import DashboardOut
from repositories import dashboard_repo
from services import feature_flags, send_gate, smtp_svc
from services.outreach_os.signals import SIGNAL_LABELS

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
SERIES_DAYS = 14


def _rate(part: int, whole: int):
    return round(part / whole, 4) if whole > 0 else None  # None = nothing sent yet, never a fabricated 0%


@router.get("/overview", response_model=DashboardOut)
async def overview(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    account_id = uuid.UUID(user["org_id"])
    now = dashboard_repo.utcnow()
    prospects = await dashboard_repo.prospect_kpis(session, account_id)
    out = await dashboard_repo.outbound_totals(session, account_id)
    status = await send_gate.status(session, account_id, "email", now)
    signals = await dashboard_repo.latest_detected_signals(session, account_id, 8)
    campaigns = await dashboard_repo.campaigns(session, account_id, 8)
    return DashboardOut(
        generated_at=now,
        kpis={
            "prospects": prospects["total"],
            "pending_review": prospects["by_review"]["pending"],
            "approved": prospects["by_review"]["approved"],
            "scored": prospects["scored"],
            "avg_score": prospects["avg_score"],
            "sent_today": status.sent_today,
            "messages": out["messages"],
            "replies": out["replied"],
            "reply_rate": _rate(out["replied"], out["messages"]),
            "bounces": out["bounced"],
            "bounce_rate": _rate(out["bounced"], out["messages"]),
            "unsubscribed": out["unsubscribed"],
        },
        series=await dashboard_repo.daily_series(session, account_id, SERIES_DAYS, now),
        latest_prospects=await dashboard_repo.latest_prospects(session, account_id, 6),
        latest_signals=[{**s, "label": SIGNAL_LABELS.get(s["key"], s["key"])} for s in signals],
        campaigns=[
            {**c, "open_rate": _rate(c["opened"], c["sent"]), "reply_rate": _rate(c["replied"], c["sent"])}
            for c in campaigns
        ],
        limits={
            "dry_run": status.dry_run,
            "kill_switch": status.halted_by_env,
            "paused": status.paused,
            "blocked_by": status.blocked_by,
            "max_per_day": status.limits.max_per_day,
            "max_per_hour": status.limits.max_per_hour,
            "min_delay_seconds": status.limits.min_delay_seconds,
            "sent_today": status.sent_today,
            "remaining_today": max(0, status.limits.max_per_day - status.sent_today),
            "sent_last_hour": status.sent_last_hour,
            "next_allowed_at": status.next_allowed_at,
            "sandbox": feature_flags.sandbox(),
            "allowlist_size": len(feature_flags.live_allowlist()),
            "smtp_configured": smtp_svc.is_configured(),
        },
        inbox=await dashboard_repo.inbox(session, account_id, 6),
    )
