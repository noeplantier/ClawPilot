"""The bounded automatic mode ("Automatisation max"): create a mandate, activate it explicitly, let the scheduled
run act inside it, stop it at once.

Off by default at two levels: the server flag FEATURE_AUTOMATION_MAX is off unless an operator turns it on, and nothing
acts without an ACTIVE mandate that a person activated on purpose. What the run does, inside one mandate and only there:
bring in new qualified prospects of the ZONE, approve their messages with the mandate's pinned template, and let the
normal sender take them one by one. What it never does: change the zone, the offer, the template, the sender, a cap or a
budget; raise a quota; contact outside the mandate; keep going after it expired, was revoked, or one of its stop rules
fired. Every authorisation, change, run, stop and refusal is written in the mandate's journal.

Automatic discovery of NEW establishments (a map search started by the run) is not part of this mode: it works on the
prospects already found in the zone. Starting external searches by itself would need quotas and terms of use to be
settled first, and a person's decision.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AutomationMandate, Campaign
from repositories import audit_repo, campaign_repo, journey_repo, launch_repo, mandate_repo
from services import campaign_launch, feature_flags, imap_svc, journey, journey_gate
from services.outreach_os import mandate as rules

ACKNOWLEDGEMENTS = (  # the four things a person must have read; all four must be ticked, by their exact codes
    "bounded",  # the mandate acts only inside its zone, message, sender, caps and expiry
    "real_sending",  # messages leave for real when sending is live
    "provider_terms",  # the provider's terms and the law on unsolicited messages are checked separately
    "can_revoke",  # it can be revoked at any time and what already left cannot be recalled
)
MAX_ACTIVE_PER_ACCOUNT = 1  # one automatic programme at a time: a second one is a second explicit decision


class MandateRefused(Exception):
    def __init__(self, code: str, label: str) -> None:
        super().__init__(label)
        self.code, self.label = code, label


def enabled() -> bool:
    return feature_flags.is_enabled("automation_max")


def provider_id() -> Optional[str]:
    info = campaign_launch.provider_info()
    return None if info.id == "none" else f"{info.id}:{info.host or ''}"


# ---------------------------------------------------------------------------------------------- views
def view(mandate: AutomationMandate) -> dict[str, Any]:
    return {
        "id": str(mandate.id),
        "name": mandate.name,
        "status": mandate.status,
        "campaign_id": str(mandate.campaign_id) if mandate.campaign_id else None,
        "zones": mandate.zones,
        "template_version": mandate.template_version,
        "daily_cap": mandate.daily_cap,
        "total_cap": mandate.total_cap,
        "ai_budget": mandate.ai_budget,
        "window": [mandate.window_start_hour, mandate.window_end_hour],
        "min_delay_seconds": mandate.min_delay_seconds,
        "search_every_hours": mandate.search_every_hours,
        "expires_at": mandate.expires_at,
        "stop_rules": rules.stop_rules_of(mandate.stop_rules),
        "provider": mandate.provider,
        "activated_at": mandate.activated_at,
        "last_run_at": mandate.last_run_at,
        "ended_at": mandate.ended_at,
        "ended_reason": mandate.ended_reason,
        "ended_label": rules.STOP_LABELS.get(mandate.ended_reason or "", mandate.ended_reason),
        "created_at": mandate.created_at,
    }


async def overview(session: AsyncSession, account_id: uuid.UUID) -> dict[str, Any]:
    """What the screen shows first: is the mode available at all, what a mandate needs, and the mandates there are."""
    items = await mandate_repo.listing(session, account_id)
    return {
        "enabled": enabled(),
        "flag": "FEATURE_AUTOMATION_MAX",
        "why_disabled": None if enabled() else rules.STOP_LABELS["feature_disabled"],
        "stop_labels": dict(rules.STOP_LABELS),
        "reply_collection_configured": imap_svc.is_configured(),
        "acknowledgements": list(ACKNOWLEDGEMENTS),
        "limits": {
            "max_daily": rules.MAX_DAILY,
            "max_total": rules.MAX_TOTAL,
            "max_days": rules.MAX_DAYS,
            "zones": rules.MAX_ZONES,
            "min_delay_seconds": rules.MIN_DELAY_SECONDS,
            "min_search_hours": rules.MIN_SEARCH_HOURS,
        },
        "defaults": {"stop_rules": rules.DEFAULT_STOP_RULES, "ai_budget": 0},
        "mandates": [view(m) for m in items],
    }


# ---------------------------------------------------------------------------------------------- pinned and health
async def _pinned(session: AsyncSession, campaign: Campaign) -> rules.Pinned:
    current = await journey_gate.current_of(session, campaign)
    return rules.Pinned(
        content_hash=current.content_hash,
        zone_hash=current.zone_hash,
        offer_hash=current.offer_hash,
        sender_fp=current.sender_fp,
        provider=provider_id(),
    )


def _pinned_of(mandate: AutomationMandate) -> rules.Pinned:
    return rules.Pinned(
        mandate.content_hash, mandate.zone_hash, mandate.offer_hash, mandate.sender_fp, mandate.provider
    )


async def collect_health(
    session: AsyncSession, mandate: AutomationMandate, campaign: Campaign, now: datetime, *, reply_collection_ok: bool
) -> rules.Health:
    counts = await mandate_repo.message_counts(session, mandate.account_id, campaign.id)
    return rules.Health(
        now=now,
        kill_switch=feature_flags.kill_switch(),
        feature_enabled=enabled(),
        auth_error=await mandate_repo.auth_error_since(session, mandate.account_id, now - timedelta(hours=24)),
        reply_collection_ok=reply_collection_ok,
        sent_total=await journey_repo.sent_count(session, mandate.account_id, campaign.id),
        bounced=counts["bounced"],
        opted_out=counts["opted_out"],
        current=await journey_gate.current_of(session, campaign),
        provider=provider_id(),
    )


# ---------------------------------------------------------------------------------------------- create and activate
async def create(
    session: AsyncSession,
    account_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    campaign: Campaign,
    *,
    name: str,
    daily_cap: int,
    total_cap: int,
    days: int,
    window: tuple[int, int],
    min_delay_seconds: int,
    search_every_hours: int,
    ai_budget: int,
    stop_rules: Optional[dict[str, Any]],
    now: datetime,
) -> AutomationMandate:
    """A mandate written down, NOT active: nothing automatic happens until a person activates it."""
    if campaign.zone is None:
        raise MandateRefused("no_zone", "Un mandat repose sur une campagne par zone.")
    template = await journey_repo.latest_template(session, account_id, campaign.id)
    if template is None:
        raise MandateRefused("template_missing", "Cette campagne n'a pas de modèle.")
    if await mandate_repo.active_for_campaign(session, account_id, campaign.id) is not None:
        raise MandateRefused(
            "already_exists", "Cette campagne a déjà un mandat en cours (actif, suspendu ou brouillon)."
        )
    spec = rules.Spec(
        zones=[campaign.zone],
        daily_cap=daily_cap,
        total_cap=total_cap,
        expires_at=now + timedelta(days=days),
        window_start_hour=window[0],
        window_end_hour=window[1],
        min_delay_seconds=min_delay_seconds,
        search_every_hours=search_every_hours,
        ai_budget=ai_budget,
    )
    found = rules.problems(spec, now)
    if found:
        raise MandateRefused(found[0].code, " ".join(p.label for p in found))
    pinned = await _pinned(session, campaign)
    mandate = AutomationMandate(
        account_id=account_id,
        campaign_id=campaign.id,
        name=name,
        status="draft",
        zones=[campaign.zone],
        zone_hash=pinned.zone_hash,
        offer_hash=pinned.offer_hash,
        template_version=template.version,
        content_hash=pinned.content_hash,
        sender_fp=pinned.sender_fp,
        provider=pinned.provider,
        daily_cap=daily_cap,
        total_cap=total_cap,
        ai_budget=ai_budget,
        window_start_hour=window[0],
        window_end_hour=window[1],
        min_delay_seconds=min_delay_seconds,
        search_every_hours=search_every_hours,
        expires_at=spec.expires_at,
        stop_rules=rules.stop_rules_of(stop_rules),
        created_by_user_id=user_id,
    )
    session.add(mandate)
    await session.flush()
    await mandate_repo.log(session, mandate, "created", actor_user_id=user_id, detail=_terms(mandate))
    await audit_repo.log(
        session,
        account_id,
        action="mandate.created",
        resource_type="automation_mandate",
        resource_id=mandate.id,
        actor_user_id=user_id,
        diff={"daily_cap": daily_cap, "total_cap": total_cap},
    )
    return mandate


def _terms(mandate: AutomationMandate) -> dict[str, Any]:
    """The authorisation as it stands, for the journal: limits and hashes, never a secret."""
    return {
        "template_version": mandate.template_version,
        "content_hash": mandate.content_hash,
        "zone_hash": mandate.zone_hash,
        "offer_hash": mandate.offer_hash,
        "provider": mandate.provider,
        "daily_cap": mandate.daily_cap,
        "total_cap": mandate.total_cap,
        "ai_budget": mandate.ai_budget,
        "expires_at": mandate.expires_at.isoformat(),
        "window": [mandate.window_start_hour, mandate.window_end_hour],
        "min_delay_seconds": mandate.min_delay_seconds,
        "search_every_hours": mandate.search_every_hours,
        "stop_rules": mandate.stop_rules,
    }


async def activate(
    session: AsyncSession,
    mandate: AutomationMandate,
    user_id: Optional[uuid.UUID],
    *,
    acknowledgements: list[str],
    now: datetime,
    reply_collection_ok: bool,
    scheduler: Optional[dict[str, Any]] = None,
) -> AutomationMandate:
    """The explicit authorisation. Refused unless the mode is available, everything is configured, the replies are being
    read, nothing halts sending, the four acknowledgements are given, and no other mandate is already running."""
    if not enabled():
        raise MandateRefused("feature_disabled", rules.STOP_LABELS["feature_disabled"])
    if mandate.status not in ("draft", "suspended"):
        raise MandateRefused("not_activatable", "Seul un mandat en brouillon ou suspendu peut être activé.")
    if sorted(set(acknowledgements)) != sorted(ACKNOWLEDGEMENTS):
        raise MandateRefused("acknowledgements", "Les quatre points de l'autorisation doivent être lus et confirmés.")
    if feature_flags.kill_switch():
        raise MandateRefused("kill_switch", rules.STOP_LABELS["kill_switch"])
    if mandate.expires_at <= now:
        raise MandateRefused("expired", rules.STOP_LABELS["expired"])
    ready = await journey.readiness(session, mandate.account_id, scheduler)
    if ready["blockers"]:
        first = ready["blockers"][0]
        raise MandateRefused(f"not_ready_{first['id']}", first["fix"] or first["label"])
    if not reply_collection_ok:
        raise MandateRefused(
            "reply_collection_down",
            "Les réponses ne sont pas lues (IMAP absent ou en panne) : sans cela, une opposition passerait inaperçue. "
            + rules.STOP_LABELS["reply_collection_down"],
        )
    others = [
        m
        for m in await mandate_repo.listing(session, mandate.account_id)
        if m.status == "active" and m.id != mandate.id
    ]
    if len(others) >= MAX_ACTIVE_PER_ACCOUNT:
        raise MandateRefused(
            "another_active", "Un autre mandat est déjà actif : un seul programme automatique à la fois."
        )
    campaign = await campaign_repo.get_campaign(session, mandate.account_id, str(mandate.campaign_id))
    if campaign is None:
        raise MandateRefused("campaign_gone", "La campagne du mandat n'existe plus.")
    pinned = await _pinned(session, campaign)  # the authorisation covers what is true at this moment
    mandate.content_hash, mandate.zone_hash, mandate.offer_hash = (
        pinned.content_hash,
        pinned.zone_hash,
        pinned.offer_hash,
    )
    mandate.sender_fp, mandate.provider = pinned.sender_fp, pinned.provider
    template = await journey_repo.latest_template(session, mandate.account_id, campaign.id)
    mandate.template_version = template.version if template else mandate.template_version
    mandate.status, mandate.activated_at, mandate.activated_by_user_id = "active", now, user_id
    mandate.ended_at = mandate.ended_reason = None
    await mandate_repo.log(session, mandate, "activated", actor_user_id=user_id, detail=_terms(mandate))
    await audit_repo.log(
        session,
        mandate.account_id,
        action="mandate.activated",
        resource_type="automation_mandate",
        resource_id=mandate.id,
        actor_user_id=user_id,
        diff=_terms(mandate),
    )
    return mandate


# ---------------------------------------------------------------------------------------------- stop
async def _stop(
    session: AsyncSession,
    mandate: AutomationMandate,
    *,
    status: str,
    code: str,
    user_id: Optional[uuid.UUID],
    now: datetime,
    revoke_approvals: bool,
    detail: Optional[str] = None,
) -> dict[str, Any]:
    mandate.status, mandate.ended_at, mandate.ended_reason = status, now, code
    cancelled = 0
    campaign = await campaign_repo.get_campaign(session, mandate.account_id, str(mandate.campaign_id))
    if campaign is not None:
        campaign.status = "paused"  # planned messages wait where they are: nothing leaves, nothing is lost
        if revoke_approvals:
            cancelled = await launch_repo.cancel_scheduled(session, mandate.account_id, campaign.id, now)
            approval = await journey_repo.latest_approval(session, mandate.account_id, campaign.id)
            if approval is not None and approval.mandate_id == mandate.id and approval.revoked_at is None:
                approval.revoked_at, approval.revoked_by_user_id, approval.revoke_reason = now, user_id, code
    await mandate_repo.log(
        session,
        mandate,
        status,
        actor_user_id=user_id,
        detail={"reason": code, "detail": detail, "cancelled": cancelled},
    )
    await audit_repo.log(
        session,
        mandate.account_id,
        action=f"mandate.{status}",
        resource_type="automation_mandate",
        resource_id=mandate.id,
        actor_user_id=user_id,
        actor_type="user" if user_id else "system",
        diff={"reason": code, "cancelled": cancelled},
    )
    return {"status": status, "reason": code, "cancelled": cancelled}


async def revoke(
    session: AsyncSession, mandate: AutomationMandate, user_id: Optional[uuid.UUID], *, now: datetime
) -> dict[str, Any]:
    """Immediate and final: nothing more leaves, planned messages are cancelled, the approvals it gave are withdrawn.
    What already left cannot be recalled."""
    if mandate.status in ("revoked", "expired"):
        raise MandateRefused("already_ended", "Ce mandat est déjà terminé.")
    return await _stop(
        session, mandate, status="revoked", code="revoked", user_id=user_id, now=now, revoke_approvals=True
    )


async def suspend(
    session: AsyncSession, mandate: AutomationMandate, user_id: Optional[uuid.UUID], *, now: datetime
) -> dict[str, Any]:
    """The pause: the run stops acting and nothing leaves; the mandate and its plan stay and can be resumed."""
    if mandate.status != "active":
        raise MandateRefused("not_active", rules.STOP_LABELS["not_active"])
    return await _stop(
        session, mandate, status="suspended", code="paused_by_user", user_id=user_id, now=now, revoke_approvals=False
    )


async def revalidate(
    session: AsyncSession, mandate: AutomationMandate, user_id: Optional[uuid.UUID], *, now: datetime
) -> AutomationMandate:
    """A person looked at what changed and accepts it: the mandate is pinned to the template, zone, offer, sender and
    provider as they are now, then waits for an explicit activation again."""
    if mandate.status != "suspended":
        raise MandateRefused("not_suspended", "Seul un mandat suspendu se revalide.")
    campaign = await campaign_repo.get_campaign(session, mandate.account_id, str(mandate.campaign_id))
    if campaign is None:
        raise MandateRefused("campaign_gone", "La campagne du mandat n'existe plus.")
    before = _terms(mandate)
    pinned = await _pinned(session, campaign)
    template = await journey_repo.latest_template(session, mandate.account_id, campaign.id)
    mandate.content_hash, mandate.zone_hash, mandate.offer_hash = (
        pinned.content_hash,
        pinned.zone_hash,
        pinned.offer_hash,
    )
    mandate.sender_fp, mandate.provider = pinned.sender_fp, pinned.provider
    mandate.template_version = template.version if template else mandate.template_version
    await mandate_repo.log(
        session, mandate, "revalidated", actor_user_id=user_id, detail={"before": before, "after": _terms(mandate)}
    )
    return mandate


# ---------------------------------------------------------------------------------------------- the scheduled run
async def tick(
    session: AsyncSession, mandate: AutomationMandate, now: datetime, *, reply_collection_ok: bool
) -> dict[str, Any]:
    """One visit of one mandate. Decides first (expired, halted, unhealthy, changed: it stops or waits), and only then
    acts, inside the mandate. Never raises for a single mandate. Returns what it did, for the journal."""
    campaign = await campaign_repo.get_campaign(session, mandate.account_id, str(mandate.campaign_id))
    if campaign is None:
        return await _stop(
            session, mandate, status="suspended", code="campaign_gone", user_id=None, now=now, revoke_approvals=False
        )
    health = await collect_health(session, mandate, campaign, now, reply_collection_ok=reply_collection_ok)
    decision = rules.verdict(
        status=mandate.status,
        expires_at=mandate.expires_at,
        total_cap=mandate.total_cap,
        rules=mandate.stop_rules,
        pinned=_pinned_of(mandate),
        health=health,
    )
    if decision.action == "end":
        done = await _stop(
            session,
            mandate,
            status="expired",
            code=decision.code or "expired",
            user_id=None,
            now=now,
            revoke_approvals=True,
        )
        return {"action": "ended", **done}
    if decision.action == "suspend":
        done = await _stop(
            session, mandate, status="suspended", code=decision.code or "suspended", user_id=None, now=now,
            revoke_approvals=False, detail=decision.detail,
        )  # fmt: skip
        return {"action": "suspended", **done}
    if decision.action == "hold":
        last = await mandate_repo.last_event(session, mandate.id, "held")
        if last is None or (last.detail or {}).get("reason") != decision.code:  # one line per cause, not one per visit
            await mandate_repo.log(session, mandate, "held", detail={"reason": decision.code})
        return {"action": "held", "reason": decision.code}

    # go: act inside the mandate
    held = await launch_repo.selection_of(session, mandate.account_id, campaign.id)
    topped = 0
    if len(held) < min(mandate.total_cap, campaign_launch.MAX_SIZE):
        added = await campaign_launch.top_up(
            session, mandate.account_id, None, campaign, size=min(mandate.total_cap, campaign_launch.MAX_SIZE), now=now
        )
        topped = len(added.picked)
    template = await journey_repo.latest_template(session, mandate.account_id, campaign.id)
    assert template is not None
    aud = await journey.audience(session, mandate.account_id, campaign, now, template.subject, template.body)
    planned_or_sent = {s.lead_id for s in aud.states if s.stage in ("planned", "launched")}
    fresh = [m for m in aud.sendable if m.lead.id not in planned_or_sent]
    approved = 0
    if fresh:
        result = await journey.approve(
            session,
            mandate.account_id,
            None,
            campaign,
            expected_hash=mandate.content_hash,
            expected_count=len(aud.sendable),
            now=now,
            mandate_id=mandate.id,
            daily_cap=mandate.daily_cap,
            total_cap=mandate.total_cap,
            valid_until=mandate.expires_at,
        )
        approved = result.get("scheduled", 0)
    mandate.last_run_at = now
    detail = {"added": topped, "fresh": len(fresh), "scheduled": approved, "sent_total": health.sent_total}
    await mandate_repo.log(session, mandate, "run", detail=detail)
    return {"action": "ran", **detail}


# ---------------------------------------------------------------------------------------------- report
async def report(session: AsyncSession, mandate: AutomationMandate, now: datetime) -> dict[str, Any]:
    """The compact periodic report: what the mandate did, what is left of its limits, how it ended or why it paused."""
    campaign = await campaign_repo.get_campaign(session, mandate.account_id, str(mandate.campaign_id))
    out: dict[str, Any] = {"mandate": view(mandate), "generated_at": now}
    if campaign is not None:
        day = await mandate_repo.message_counts(session, mandate.account_id, campaign.id, now - timedelta(hours=24))
        total = await mandate_repo.message_counts(session, mandate.account_id, campaign.id)
        out["last_24h"] = day
        out["total"] = total
        out["remaining"] = {
            "messages": max(0, mandate.total_cap - total["sent"]),
            "days": max(0, (mandate.expires_at - now).days),
        }
        out["progress"] = await journey.progress(session, mandate.account_id, campaign, now)
    out["journal"] = [
        {"at": e.created_at, "action": e.action, "actor": e.actor_type, "detail": e.detail}
        for e in await mandate_repo.events(session, mandate.id, 30)
    ]
    out["note"] = (
        "Ce mode n'a rien élargi : zone, offre, modèle, expéditeur, plafonds et budget sont ceux de l'autorisation. "
        "La découverte de nouveaux établissements n'est pas automatique."
    )
    return out


async def run_all(session_factory: Any, now: datetime, *, reply_collection_ok: bool) -> dict[str, int]:
    """Visit every active mandate, each in its own transaction (one failing never blocks or corrupts another)."""
    counts = {"visited": 0, "failed": 0}
    async with session_factory() as session:
        ids = [(m.account_id, m.id) for m in await mandate_repo.active_all(session)]
    for account_id, mandate_id in ids:
        async with session_factory() as session:
            try:
                mandate = await mandate_repo.get(session, account_id, mandate_id)
                if mandate is not None and mandate.status == "active":
                    await tick(session, mandate, now, reply_collection_ok=reply_collection_ok)
                await session.commit()
                counts["visited"] += 1
            except Exception:  # noqa: BLE001 (a mandate that fails is left untouched; the next visit tries again)
                await session.rollback()
                counts["failed"] += 1
    return counts
