"""Individual campaigns: pick the recipients, review one draft each, plan the messages, send them one by one.

Nothing in this module invents an engine. Drafts come from the automatic AI flow (services/draft_runner.py), a message
leaves through `dispatch_draft` (the single dispatch every path uses: kill switch, pause, eligibility, suppression,
consent, compliance, limits, adapter, sandbox, at most once), the limits and the pause are `send_gate`. What is added
here:

* the SELECTION of distinct recipients, with the reason of every exclusion;
* the REVIEW of each draft (recipient, subject, body, evidence, authorization of the channel, blockers);
* the PLAN: when each approved message may leave, given the send window and the limits;
* the SENDER of the plan, run by a scheduled task: every gate is checked again at the moment a message would really
  leave, a gate that refuses for a time reschedules the message, a gate that refuses for good stops it, and nothing is
  ever retried after an unclear outcome;
* the TRACKING, honest: planned / accepted by SMTP / failed / replied / opted out. "Delivered" does not exist here.

Scheduling a campaign writes plan rows. It sends nothing by itself.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Campaign, CampaignDispatch, DraftJob, Lead, MessageDraft, OutboundMessage
from repositories import (
    audit_repo,
    campaign_repo,
    consent_repo,
    draft_repo,
    launch_repo,
    outbound_repo,
    prospect_repo,
    send_policy_repo,
    suppression_repo,
)
from services import draft_runner, feature_flags, send_gate, sendgrid_svc, smtp_svc
from services.outreach_os import ai_draft, campaign_plan, channels, dispatch, drafts, eligibility
from services.outreach_os import heat as heat_rules
from services.outreach_os import provider_policy
from services.outreach_os import sandbox as sandbox_rules
from services.outreach_os.normalize import normalize_domain, normalize_email, normalize_phone
from services.outreach_os.types import SignalState
from services.timezones import resolve_timezone

logger = logging.getLogger(__name__)

SELECTION_SCAN = 1000  # approved prospects looked at to find the recipients
MAX_SIZE = 100
WAIT = timedelta(
    minutes=15
)  # a halt (kill switch, pause, provider) is looked at again later, never turned into a failure
STUCK_AFTER = timedelta(
    minutes=10
)  # a message "sending" for this long was interrupted: its outcome is established, not guessed
DUE_PER_RUN = 20
REPLANNABLE = (
    "cancelled",
    "skipped",
    "failed",
)  # a person may plan these again; an accepted or unknown one is never planned twice


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------------------------- provider and gates
def provider_info() -> provider_policy.ProviderInfo:
    """The provider that would carry a real message, from the configuration (a host name only: never a secret)."""
    config = smtp_svc.SmtpConfig.from_env()
    return provider_policy.identify(
        smtp_host=config.host if config else None, sendgrid_configured=sendgrid_svc.is_configured()
    )


async def gates(session: AsyncSession, account_id: uuid.UUID, now: datetime) -> dict[str, Any]:
    """What stands between a planned message and the network, as the organisation has it configured right now."""
    status = await send_gate.status(session, account_id, "email", now)
    policy = await send_policy_repo.get_policy(session, account_id, "email")
    provider = provider_info()
    sender = drafts.SenderIdentity.from_env()
    live = not feature_flags.dry_run()
    return {
        "provider": provider,
        "dry_run": status.dry_run,
        "live": live,
        "kill_switch": status.halted_by_env,
        "paused": status.paused,
        "sandbox": feature_flags.sandbox(),
        "allowlist_size": len(feature_flags.live_allowlist()),
        "sender_configured": sender is not None,
        "smtp_complete": smtp_svc.is_configured(),
        "limits": status.limits,
        "policy": policy,
        "sent_today": status.sent_today,
        "sent_last_hour": status.sent_last_hour,
        "next_allowed_at": status.next_allowed_at,
    }


# ---------------------------------------------------------------------------------------------- selection
@dataclass
class Excluded:
    lead_id: uuid.UUID
    name: str
    city: Optional[str]
    email: Optional[str]
    code: str

    @property
    def label(self) -> str:
        return campaign_plan.exclusion_label(self.code)


@dataclass
class Selection:
    picked: list[Lead] = field(default_factory=list)
    excluded: list[Excluded] = field(default_factory=list)
    not_approved: int = 0
    scanned: int = 0


@dataclass
class Facts:
    """What the exclusions rest on, read once for a whole group of prospects."""

    replied: set[uuid.UUID]
    contacted: set[uuid.UUID]
    bounced: set[str]
    elsewhere: set[uuid.UUID]
    opted_message: set[uuid.UUID]
    consent: dict[uuid.UUID, str]
    notes: dict[uuid.UUID, list[Optional[str]]]


async def _facts(
    session: AsyncSession, account_id: uuid.UUID, campaign_id: Optional[uuid.UUID], leads: Sequence[Lead]
) -> Facts:
    ids = [lead.id for lead in leads]
    emails = [e for e in (normalize_email(lead.email) for lead in leads) if e]
    return Facts(
        replied=await launch_repo.replied_lead_ids(session, account_id, ids),
        contacted=await launch_repo.contacted_lead_ids(session, account_id, ids),
        bounced=await launch_repo.bounced_emails(session, account_id, emails),
        elsewhere=await launch_repo.taken_elsewhere(session, account_id, campaign_id, ids),
        opted_message=await launch_repo.opted_out_message_lead_ids(session, account_id, ids),
        consent=await launch_repo.primary_consent(session, ids),
        notes=await launch_repo.license_notes(session, ids),
    )


def authorization_of(lead: Lead, facts: Facts, provider: provider_policy.ProviderInfo) -> provider_policy.Authorization:
    return provider_policy.authorize(
        provider,
        consent_status=facts.consent.get(lead.id, consent_repo.DEFAULT_STATUS),
        legal_basis=provider_policy.legal_basis_of(facts.notes.get(lead.id, [])),
    )


def _email_gap(lead: Lead) -> Optional[str]:
    if not (lead.email or "").strip():
        return "no_email"
    email = normalize_email(lead.email)
    if email is None or eligibility.PLACEHOLDER_EMAIL_DOMAIN.search(email.rsplit("@", 1)[-1]):
        return "invalid_email"
    return None


def exclusion_for(
    lead: Lead,
    flags: tuple[bool, bool, bool, bool],
    facts: Facts,
    provider: provider_policy.ProviderInfo,
    seen_emails: set[str],
    seen_keys: set[str],
) -> Optional[str]:
    """Why this prospect cannot be a recipient, or None. The order is the order a person would check: who they are,
    whether they may be written to at all, whether they already were, whether this provider may carry it, whether it
    is a duplicate.
    """
    qualified, suppressed, opted_out, demo = flags
    if lead.review_status == "rejected":
        return "rejected"
    if lead.review_status != "approved":
        return "not_approved"
    if demo:
        return "demo"
    if suppressed:
        return "suppressed"
    if opted_out or lead.id in facts.opted_message:
        return "opted_out"
    if not qualified:
        return "not_qualified"
    gap = _email_gap(lead)
    if gap:
        return gap
    email = normalize_email(lead.email) or ""
    if email in facts.bounced:
        return "bounced"
    if lead.id in facts.replied:
        return "already_replied"
    if lead.id in facts.contacted:
        return "already_contacted"
    if lead.id in facts.elsewhere:
        return "campaign_conflict"
    if not authorization_of(lead, facts, provider).ok:
        return "provider_requires_opt_in"
    if email in seen_emails:
        return "duplicate_email"
    if campaign_plan.establishment_key(lead.full_name, lead.city) in seen_keys:
        return "duplicate_establishment"
    return None


def _remember(lead: Lead, seen_emails: set[str], seen_keys: set[str]) -> None:
    seen_emails.add(normalize_email(lead.email) or "")
    seen_keys.add(campaign_plan.establishment_key(lead.full_name, lead.city))


async def select_recipients(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    size: int,
    now: datetime,
    campaign_id: Optional[uuid.UUID] = None,
    keep: Sequence[uuid.UUID] = (),
) -> Selection:
    """Up to `size` DISTINCT establishments, best first (observed intent, then heat), each with a valid e-mail and the
    right to receive a campaign through the active provider. `keep` are the recipients a campaign already holds (a
    top-up adds to them). Every prospect passed over on the way is reported with its reason."""
    size = max(0, min(size, MAX_SIZE))
    provider = provider_info()
    result = Selection()
    seen_emails: set[str] = set()
    seen_keys: set[str] = set()
    kept = set(keep)
    for lead_id in keep:
        existing = await session.get(Lead, lead_id)
        if existing is not None:
            _remember(existing, seen_emails, seen_keys)
    rows = await launch_repo.pool(session, account_id, now, SELECTION_SCAN)
    result.scanned = len(rows)
    facts = await _facts(session, account_id, campaign_id, [row[0] for row in rows])
    wanted = size - len(kept)
    for lead, qualified, suppressed, opted_out, demo in rows:
        if lead.id in kept:
            continue
        if len(result.picked) >= wanted:
            break
        code = exclusion_for(lead, (qualified, suppressed, opted_out, demo), facts, provider, seen_emails, seen_keys)
        if code is None:
            result.picked.append(lead)
            _remember(lead, seen_emails, seen_keys)
        else:
            result.excluded.append(Excluded(lead.id, lead.full_name, lead.city, lead.email, code))
    counts = await launch_repo.review_counts(session, account_id)
    result.not_approved = sum(n for status, n in counts.items() if status != "approved")
    return result


async def create_launch(
    session: AsyncSession, account_id: uuid.UUID, user_id: Optional[uuid.UUID], *, name: str, size: int, now: datetime
) -> tuple[Campaign, Selection]:
    """A campaign of individual messages with its recipients. Status stays `draft`: nothing is planned or sent."""
    selection = await select_recipients(session, account_id, size=size, now=now)
    campaign = await campaign_repo.create_campaign(
        session,
        account_id,
        {
            "name": name,
            "goal": "Campagne individuelle : un brouillon personnalisé par destinataire",
            "status": "draft",
            "kind": "individual",
            "channels": ["email"],
            "lead_ids": [str(lead.id) for lead in selection.picked],
        },
    )
    await audit_repo.log(
        session,
        account_id,
        action="launch.created",
        resource_type="campaign",
        resource_id=campaign.id,
        actor_user_id=user_id,
        diff={"requested": size, "selected": len(selection.picked), "excluded": len(selection.excluded)},
    )
    return campaign, selection


async def top_up(
    session: AsyncSession,
    account_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    campaign: Campaign,
    *,
    size: int,
    now: datetime,
) -> Selection:
    """Complete the selection up to `size` recipients with new distinct establishments (those already held are kept)."""
    held = await launch_repo.selection_of(session, account_id, campaign.id)
    selection = await select_recipients(session, account_id, size=size, now=now, campaign_id=campaign.id, keep=held)
    if selection.picked:
        await campaign_repo.assign_leads(
            session, account_id, str(campaign.id), [str(lead.id) for lead in selection.picked]
        )
        await audit_repo.log(
            session,
            account_id,
            action="launch.topped_up",
            resource_type="campaign",
            resource_id=campaign.id,
            actor_user_id=user_id,
            diff={"added": len(selection.picked), "size": size},
        )
    return selection


# ---------------------------------------------------------------------------------------------- the state of each
# recipient
@dataclass
class LeadState:
    lead_id: uuid.UUID
    lead: Optional[Lead]
    stage: str  # excluded | no_draft | to_review | rejected | blocked | ready | planned | launched
    exclusion: Optional[str]
    draft: Optional[MessageDraft]
    job: Optional[DraftJob]
    problems: list[campaign_plan.Problem]
    authorization: provider_policy.Authorization
    sourced_now: list[str]
    site_state: Optional[str]
    source: Optional[dict[str, Any]]
    dispatch: Optional[CampaignDispatch]

    @property
    def sendable(self) -> bool:
        """Approved, clean, allowed, and not planned or sent yet (a stopped or cancelled one may be planned again)."""
        return self.stage == "ready"


async def _evidence(session: AsyncSession, lead: Lead) -> tuple[list[str], Optional[str], Optional[dict[str, Any]]]:
    """(what a detected signal backs today, the state of the website, the source) for one prospect."""
    sources = await prospect_repo.sources_of(session, lead.id)
    latest = max(sources, key=lambda s: s.fetched_at) if sources else None
    results = await prospect_repo.effective_results(session, lead.id)  # a dismissed signal is never stated
    raw = (latest.fields.get("last_updated") if latest else None) or None
    updated = date.fromisoformat(raw) if isinstance(raw, str) else None
    sourced = [
        sentence for _, sentence in drafts.observed_facts(results, latest.source_name if latest else "", updated)
    ]
    detected = {r.key: r.evidence for r in results if r.state is SignalState.DETECTED}
    state = ai_draft.site_state(website=lead.website if heat_rules.is_known(lead.website) else None, detected=detected)
    source = (
        {"name": latest.source_name, "url": latest.source_url, "fetched_at": latest.fetched_at}
        if latest is not None
        else None
    )
    return sourced, state, source


async def evaluate(session: AsyncSession, account_id: uuid.UUID, campaign: Campaign, now: datetime) -> list[LeadState]:
    """The state of every recipient of the campaign: the live exclusions, the draft, what blocks it, what the channel
    allows."""
    ids = await launch_repo.selection_of(session, account_id, campaign.id)
    flags = await launch_repo.flags_for(session, account_id, ids, now)
    leads = [flags[i][0] for i in ids if i in flags]
    facts = await _facts(session, account_id, campaign.id, leads)
    provider = provider_info()
    sender = drafts.SenderIdentity.from_env()
    drafts_of = await launch_repo.latest_drafts(session, account_id, ids)
    jobs_of = await launch_repo.latest_jobs(session, account_id, ids)
    plans = await launch_repo.dispatches_of(session, account_id, campaign.id)
    seen_emails: set[str] = set()
    seen_keys: set[str] = set()
    out: list[LeadState] = []
    for lead_id in ids:
        row = flags.get(lead_id)
        plan = plans.get(lead_id)
        if row is None:  # the prospect was deleted
            out.append(_gone(lead_id, plan))
            continue
        lead, qualified, suppressed, opted_out, demo = row
        auth = authorization_of(lead, facts, provider)
        sourced, site_state, source = await _evidence(session, lead)
        draft, job = drafts_of.get(lead_id), jobs_of.get(lead_id)
        if (
            plan is not None and plan.status not in REPLANNABLE
        ):  # planned, in flight or already sent: the tracking speaks
            stage = "planned" if plan.status == "scheduled" else "launched"
            out.append(LeadState(lead_id, lead, stage, None, draft, job, [], auth, sourced, site_state, source, plan))
            _remember(lead, seen_emails, seen_keys)
            continue
        code = exclusion_for(lead, (qualified, suppressed, opted_out, demo), facts, provider, seen_emails, seen_keys)
        problems: list[campaign_plan.Problem] = []
        if code is not None:
            stage = "excluded"
        elif draft is None:
            stage = "no_draft"
        elif draft.status == "rejected":
            stage = "rejected"
        else:
            problems = campaign_plan.review_problems(
                campaign_plan.ReviewInput(
                    subject=draft.subject,
                    body=draft.body,
                    facts=list(draft.facts or []),
                    sourced_now=sourced,
                    compliance=drafts.compliance_problems(draft.body, sender) if sender else [],
                    sender_configured=sender is not None,
                    edited_by_hand=draft.edited_at is not None,
                )
            )
            if draft.status == "draft":
                stage = "to_review"
            else:
                stage = "blocked" if campaign_plan.blocking(problems) else "ready"
        if code is None:
            _remember(lead, seen_emails, seen_keys)
        out.append(LeadState(lead_id, lead, stage, code, draft, job, problems, auth, sourced, site_state, source, plan))
    return out


def _gone(lead_id: uuid.UUID, plan: Optional[CampaignDispatch]) -> LeadState:
    auth = provider_policy.Authorization(False, provider_policy.BASIS_PUBLIC_DIRECTORY, None, "Prospect supprimé")
    return LeadState(lead_id, None, "excluded", "not_approved", None, None, [], auth, [], None, None, plan)


def stage_counts(states: Sequence[LeadState]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for state in states:
        counts[state.stage] = counts.get(state.stage, 0) + 1
    return counts


def exclusion_counts(states: Sequence[LeadState]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for state in states:
        if state.exclusion:
            counts[state.exclusion] = counts.get(state.exclusion, 0) + 1
    return counts


# ---------------------------------------------------------------------------------------------- drafts
def generate_missing_drafts(account_id: uuid.UUID, lead_ids: Sequence[uuid.UUID]) -> bool:
    """Start, in the background, the automatic drafts of these recipients (the existing AI flow, scoped). A draft
    is a proposal: nothing is approved, nothing is sent. False when a sweep is already running."""
    return draft_runner.kick(account_id, only=set(lead_ids), budget=draft_runner.CAMPAIGN_BATCH_BUDGET)


async def review_drafts(
    session: AsyncSession,
    account_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    campaign: Campaign,
    draft_ids: Sequence[uuid.UUID],
    decision: str,
    now: datetime,
) -> list[dict[str, Any]]:
    """Approve or reject drafts of this campaign. An approval is refused, with the reason, for a draft that has a
    blocker."""
    states = {s.draft.id: s for s in await evaluate(session, account_id, campaign, now) if s.draft is not None}
    out: list[dict[str, Any]] = []
    for draft_id in draft_ids:
        state = states.get(draft_id)
        if state is None or state.draft is None:
            out.append(
                {
                    "draft_id": str(draft_id),
                    "ok": False,
                    "reason": "Brouillon étranger à cette campagne ou remplacé par un plus récent",
                }
            )
            continue
        draft = state.draft
        if draft.status != "draft":
            out.append({"draft_id": str(draft_id), "ok": False, "reason": f"Déjà {draft.status}"})
            continue
        if decision == "approve":
            if state.exclusion:
                out.append(
                    {"draft_id": str(draft_id), "ok": False, "reason": campaign_plan.exclusion_label(state.exclusion)}
                )
                continue
            blockers = campaign_plan.blocking(state.problems)
            if blockers:
                out.append({"draft_id": str(draft_id), "ok": False, "reason": "; ".join(p.label for p in blockers)})
                continue
        status = "approved" if decision == "approve" else "rejected"
        await draft_repo.review(session, draft, status=status, user_id=user_id, note=None)  # type: ignore[arg-type]
        await audit_repo.log(
            session,
            account_id,
            action=f"draft.{status}",
            resource_type="draft",
            resource_id=draft.id,
            actor_user_id=user_id,
            diff={"prospect_id": str(draft.lead_id), "dry_run": draft.dry_run, "via": "launch"},
        )
        out.append({"draft_id": str(draft_id), "ok": True, "reason": None})
    return out


# ---------------------------------------------------------------------------------------------- plan
class PlanChanged(Exception):
    """What the person saw is no longer what would be planned: they must read the new preview first."""

    def __init__(self, actual: int) -> None:
        super().__init__(f"{actual} messages are sendable now")
        self.actual = actual


def _slot_policy(policy: send_policy_repo.EffectivePolicy) -> campaign_plan.SlotPolicy:
    return campaign_plan.SlotPolicy(
        max_per_day=policy.max_per_day,
        max_per_hour=policy.max_per_hour,
        min_delay_seconds=policy.min_delay_seconds,
        window_start_hour=policy.window_start_hour,
        window_end_hour=policy.window_end_hour,
        timezone=policy.account_default_timezone,
    )


async def preview(
    session: AsyncSession, account_id: uuid.UUID, campaign: Campaign, now: datetime
) -> tuple[dict[str, Any], list[LeadState], list[datetime]]:
    """What "Planifier les messages approuvés" would do, computed from the data as it is now (never from what a screen
    showed)."""
    states = await evaluate(session, account_id, campaign, now)
    ready = [s for s in states if s.sendable]
    g = await gates(session, account_id, now)
    policy = _slot_policy(g["policy"])
    day_start, _ = send_gate.day_bounds(now, policy.timezone)
    sent = await outbound_repo.dispatch_times_since(session, account_id, "email", day_start)
    taken = await launch_repo.planned_times(session, account_id)
    windows = [zone_name(s.lead, g["policy"]) for s in ready if s.lead is not None]
    slots = campaign_plan.plan_slots(len(ready), now=now, policy=policy, already_sent=sent + taken, windows=windows)
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if not g["sender_configured"]:
        blockers.append(
            {"code": "sender_not_configured", "label": "Identité de l'expéditeur non configurée (OUTREACH_SENDER_*)"}
        )
    if len(slots) < len(ready):
        blockers.append(
            {
                "code": "no_slot",
                "label": "Les limites et la fenêtre d'envoi ne laissent aucun créneau (limite à 0 ou fenêtre vide)",
            }
        )
    if g["kill_switch"]:
        warnings.append({"code": "kill_switch", "label": "Arrêt d'urgence actif : rien ne partira tant qu'il l'est"})
    if g["paused"]:
        warnings.append(
            {"code": "paused", "label": "Envois en pause pour l'organisation : rien ne partira tant qu'elle dure"}
        )
    if g["live"] and not g["smtp_complete"]:
        warnings.append(
            {"code": "live_not_available", "label": "Envoi réel activé sans SMTP complet : l'envoi sera refusé"}
        )
    if g["dry_run"]:
        warnings.append(
            {
                "code": "dry_run",
                "label": "Envoi réel désactivé (dry-run) : les messages seront simulés, rien ne partira",
            }
        )
    scope_code, scope_label = sandbox_rules.scope(live=g["live"], sandbox_on=g["sandbox"], entries=g["allowlist_size"])
    if g["live"]:  # who would really receive: said whether the sandbox restricts them or not
        warnings.append({"code": scope_code, "label": scope_label})
    if g["provider"].cold_outreach != provider_policy.OPT_IN_REQUIRED:
        warnings.append({"code": "provider_terms", "label": g["provider"].restriction})
    summary = campaign_plan.schedule_summary(slots, policy.timezone)
    plan = {
        "selected": len(states),
        "sendable": len(ready),
        "stages": stage_counts(states),
        "exclusions": exclusion_counts(states),
        "schedule": summary,
        "blockers": blockers,
        "warnings": warnings,
        "gates": g,
        "generated_at": now,
    }
    return plan, ready, slots


async def schedule(
    session: AsyncSession,
    account_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    campaign: Campaign,
    *,
    expected: int,
    now: datetime,
) -> dict[str, Any]:
    """Plan the approved messages: one row per recipient, at the earliest time it may leave. Sends nothing. The count
    person confirmed must still be the real one; otherwise nothing is written (PlanChanged)."""
    plan, ready, slots = await preview(session, account_id, campaign, now)
    if plan["blockers"]:
        return {**plan, "scheduled": 0, "refused": plan["blockers"][0]["code"]}
    if len(ready) != expected:
        raise PlanChanged(len(ready))
    for state, slot in zip(ready, slots):
        assert state.lead is not None and state.draft is not None
        await launch_repo.plan(
            session,
            account_id,
            campaign.id,
            lead_id=state.lead_id,
            draft_id=state.draft.id,
            to_email=normalize_email(state.lead.email) or "",
            planned_at=slot,
            user_id=user_id,
            existing=state.dispatch,
        )
    if ready:
        campaign.status = "running"
    await audit_repo.log(
        session,
        account_id,
        action="launch.scheduled",
        resource_type="campaign",
        resource_id=campaign.id,
        actor_user_id=user_id,
        diff={
            "scheduled": len(ready),
            "first_at": plan["schedule"]["first_at"].isoformat() if plan["schedule"]["first_at"] else None,
            "dry_run": plan["gates"]["dry_run"],
        },
    )
    return {**plan, "scheduled": len(ready), "refused": None}


async def cancel(
    session: AsyncSession, account_id: uuid.UUID, user_id: Optional[uuid.UUID], campaign: Campaign, now: datetime
) -> int:
    """Stop every message of the campaign that has not left: planned ones are cancelled, the campaign is paused."""
    cancelled = await launch_repo.cancel_scheduled(session, account_id, campaign.id, now)
    campaign.status = "paused"
    await audit_repo.log(
        session,
        account_id,
        action="launch.cancelled",
        resource_type="campaign",
        resource_id=campaign.id,
        actor_user_id=user_id,
        diff={"cancelled": cancelled},
    )
    return cancelled


# ---------------------------------------------------------------------------------------------- tracking
async def tracking(
    session: AsyncSession, account_id: uuid.UUID, campaign: Campaign, *, state: Optional[str], offset: int, limit: int
) -> tuple[dict[str, int], list[dict[str, Any]], int]:
    """(counts by honest state, one page of rows, total of the filter). Planned and sent recipients only."""
    plans = await launch_repo.dispatches_of(session, account_id, campaign.id)
    messages = await launch_repo.messages_of(
        session, account_id, [p.message_id for p in plans.values() if p.message_id]
    )
    names = await launch_repo.names_of(session, account_id, list(plans))
    opted = await launch_repo.opted_out_message_lead_ids(session, account_id, list(plans))
    rows: list[dict[str, Any]] = []
    for lead_id, plan in plans.items():
        message = messages.get(plan.message_id) if plan.message_id else None
        name, city = names.get(lead_id, ("(supprimé)", None))
        status = campaign_plan.tracking_state(
            dispatch_status=plan.status,
            message_status=message.status if message else None,
            message_dry_run=message.dry_run if message else None,
            opted_out=lead_id in opted,
        )
        rows.append(
            {
                "lead_id": lead_id,
                "name": name,
                "city": city,
                "email": plan.to_email,
                "state": status,
                "label": campaign_plan.TRACKING_LABELS[status],
                "reason": (
                    campaign_plan.exclusion_label(plan.last_reason)
                    if plan.last_reason and status == "skipped"
                    else plan.last_reason
                ),
                "planned_at": plan.planned_at,
                "message_id": message.id if message else None,
                "dispatched_at": message.dispatched_at if message else None,
                "adapter": message.adapter if message else None,
                "dry_run": message.dry_run if message else None,
            }
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    rows.sort(key=lambda r: (_utc(r["planned_at"]), r["name"]))
    if state:
        rows = [r for r in rows if r["state"] == state]
    return counts, rows[offset : offset + limit], len(rows)


# ---------------------------------------------------------------------------------------------- sending the plan
@dataclass
class Outcome:
    code: str  # accepted | failed | unknown | skipped | waiting | lost
    reason: Optional[str] = None
    halt_account: bool = (
        False  # the account-wide reason (limit, pause, kill switch): stop looking at this account for now
    )


def zone_name(lead: Lead, policy: send_policy_repo.EffectivePolicy) -> str:
    """The time zone whose send window applies to this recipient: its country's when the policy asks for it, else the
    organisation's."""
    if policy.timezone_source == "lead_country":
        return resolve_timezone(lead.country, default=policy.account_default_timezone)
    return policy.account_default_timezone


async def _window_wait(
    session: AsyncSession, lead: Lead, now: datetime, policy: send_policy_repo.EffectivePolicy
) -> Optional[datetime]:
    """None inside the send window of this recipient, else when it next opens."""
    import zoneinfo

    try:
        zone = zoneinfo.ZoneInfo(zone_name(lead, policy))
    except Exception:  # noqa: BLE001
        zone = zoneinfo.ZoneInfo("UTC")
    local = now.astimezone(zone)
    if send_policy_repo.in_window(policy, local.hour):
        return None
    return campaign_plan.next_window_start(local, policy.window_start_hour).astimezone(timezone.utc)


async def _send_one(
    session: AsyncSession, row: CampaignDispatch, now: datetime, live_adapter: Optional[channels.ChannelAdapter]
) -> Outcome:
    """Every gate, in order, at the moment this message would really leave. Returns what happened."""
    account_id = row.account_id
    campaign = await campaign_repo.get_campaign(session, account_id, str(row.campaign_id))
    if campaign is None:
        return Outcome("skipped", "campaign_gone")
    if campaign.status != "running":  # the campaign must be active: a paused one waits, it is not lost
        return Outcome("waiting", "campaign_paused")
    lead = await prospect_repo.get(session, account_id, str(row.lead_id))
    if lead is None:
        return Outcome("skipped", "prospect_gone")
    if lead.review_status != "approved":
        return Outcome("skipped", "prospect_not_approved")
    if not lead.email:
        return Outcome("skipped", "no_email")
    if normalize_email(lead.email) != normalize_email(row.to_email):
        return Outcome("skipped", "recipient_changed")
    draft = await draft_repo.get(session, account_id, str(row.draft_id)) if row.draft_id else None
    if draft is None or draft.status != "approved":
        return Outcome("skipped", "draft_not_approved")

    ids = [lead.id]
    email = normalize_email(lead.email) or ""
    if await suppression_repo.is_suppressed(
        session, account_id, email=email, phone=normalize_phone(lead.phone), domain=normalize_domain(lead.website)
    ):
        return Outcome("skipped", "suppressed")
    contact = await consent_repo.get_primary_contact_id(session, lead.id)
    if contact is not None and not consent_repo.can_send(
        "email", await consent_repo.get_status(session, contact, "email")
    ):
        return Outcome("skipped", "opted_out")
    if email in await launch_repo.bounced_emails(session, account_id, [email]):
        return Outcome("skipped", "bounced")
    if await launch_repo.replied_lead_ids(session, account_id, ids):
        return Outcome("skipped", "already_replied")
    if await launch_repo.opted_out_message_lead_ids(session, account_id, ids):
        return Outcome("skipped", "opted_out")
    if await launch_repo.taken_elsewhere(session, account_id, row.campaign_id, ids):
        return Outcome("skipped", "campaign_conflict")
    facts = Facts(
        set(),
        set(),
        set(),
        set(),
        set(),
        await launch_repo.primary_consent(session, ids),
        await launch_repo.license_notes(session, ids),
    )
    if not authorization_of(lead, facts, provider_info()).ok:
        return Outcome("skipped", "provider_requires_opt_in")

    policy = await send_policy_repo.get_policy(session, account_id, "email")
    opens_at = await _window_wait(session, lead, now, policy)
    if opens_at is not None:
        return Outcome("waiting", f"outside_window@{opens_at.isoformat()}")

    try:
        message, _ = await dispatch.dispatch_draft(
            session,
            account_id,
            draft,
            now=now,
            user_id=None,
            idempotency_key=f"campaign:{row.id}",
            live_adapter=live_adapter,
        )
    except dispatch.DispatchBlocked as blocked:
        kind = campaign_plan.refusal_kind(blocked.code)
        if kind == "wait":
            until = blocked.retry_at
            reason = blocked.code if until is None else f"{blocked.code}@{_utc(until).isoformat()}"
            return Outcome(
                "waiting",
                reason,
                halt_account=blocked.code in ("kill_switch", "paused", "limit_daily", "limit_hourly", "limit_delay"),
            )
        return Outcome("skipped", blocked.code)
    row.message_id = message.id
    return _outcome_of(message)


def _outcome_of(message: OutboundMessage) -> Outcome:
    if message.status in ("sent", "replied", "bounced"):
        return Outcome("accepted")
    if message.status == "failed":
        return Outcome("failed", (message.error or "send_failed")[:200])
    return Outcome(
        "unknown", "outcome_unknown"
    )  # still "sending": the adapter did not tell, a person checks the mailbox


def _wait_until(reason: str, now: datetime) -> tuple[str, datetime]:
    """("code", when) from a waiting reason; a reason with no time waits WAIT, never less."""
    code, _, stamp = reason.partition("@")
    if stamp:
        try:
            return code, max(datetime.fromisoformat(stamp), now + timedelta(seconds=1))
        except ValueError:
            pass
    return code, now + WAIT


async def _record(session: AsyncSession, row: CampaignDispatch, outcome: Outcome, now: datetime) -> None:
    if outcome.code == "waiting":
        code, until = _wait_until(outcome.reason or "", now)
        row.status, row.planned_at, row.last_reason = "scheduled", until, code
    elif outcome.code == "accepted":
        row.status, row.last_reason = "accepted", None
    else:
        row.status, row.last_reason = outcome.code, outcome.reason
        await audit_repo.log(
            session,
            row.account_id,
            action=f"launch.message_{outcome.code}",
            resource_type="campaign_dispatch",
            resource_id=row.id,
            actor_type="system",
            diff={"campaign_id": str(row.campaign_id), "prospect_id": str(row.lead_id), "reason": outcome.reason},
        )
    row.last_checked_at = now


async def reconcile_stuck(session: AsyncSession, now: datetime) -> int:
    """A message left "sending" by an interruption: the send ledger says what happened. A message row that settles
    it (accepted / failed / unknown, never sent twice); no row means nothing could have left, so it is planned again."""
    fixed = 0
    for row in await launch_repo.stuck(session, now, STUCK_AFTER):
        message = await outbound_repo.get_by_key(session, row.account_id, f"campaign:{row.id}")
        if message is None and row.draft_id:
            message = await outbound_repo.get_for_draft(session, row.account_id, row.draft_id)
        if message is None:
            row.status, row.planned_at, row.last_reason = "scheduled", now, "interrupted_before_send"
        else:
            row.message_id = message.id
            await _record(session, row, _outcome_of(message), now)
        fixed += 1
    if fixed:
        await session.commit()
    return fixed


async def process_due(
    session: AsyncSession,
    *,
    now: datetime,
    live_adapter: Optional[channels.ChannelAdapter] = None,
    limit: int = DUE_PER_RUN,
    account_id: Optional[uuid.UUID] = None,
) -> dict[str, int]:
    """Send what is due. For each planned message: claim it (atomic), check every gate again, send it through the common
    dispatch, record what happened. A reason that time can fix reschedules the message; one that cannot stops it; an
    account-wide refusal (limit, pause, kill switch) ends the run for that account. Never raises for a single message.
    """
    counts = {"accepted": 0, "failed": 0, "unknown": 0, "skipped": 0, "waiting": 0, "reconciled": 0}
    counts["reconciled"] = await reconcile_stuck(session, now)
    halted: set[uuid.UUID] = set()
    for dispatch_id, owner in await launch_repo.due_ids(session, now, limit, account_id):
        if (
            owner in halted
        ):  # a limit, a pause or the kill switch ended this account's run: its other messages wait their turn
            continue
        row = await launch_repo.claim(session, dispatch_id, now)
        await session.commit()  # the claim is visible to everyone before anything can happen
        if row is None:
            continue
        try:
            outcome = await _send_one(session, row, now, live_adapter)
        except (
            Exception
        ) as exc:  # noqa: BLE001 (left "sending": reconcile_stuck settles it from the ledger, never a blind retry)
            await session.rollback()
            logger.warning("launch_dispatch id=%s failed: %s", dispatch_id, type(exc).__name__)
            continue
        if outcome.halt_account:
            halted.add(row.account_id)
        row = await session.get(CampaignDispatch, dispatch_id) or row
        await _record(session, row, outcome, now)
        await session.commit()
        counts[outcome.code] = counts.get(outcome.code, 0) + 1
    return counts
