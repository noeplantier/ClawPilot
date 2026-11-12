"""The journey "zone -> draft -> approval": three decisions, the rest is done by the system.

1. ZONE: an explicit perimeter drawn on the map (a box, with its category). Only prospects positioned inside it are
   candidates; nothing says "every establishment of the zone": the coverage of the sources is reported as it is.
2. DRAFT: one controlled template, pre-filled from the configured offer, that the person may edit. Each message is
   rendered for its establishment from fixed placeholders (services/outreach_os/campaign_template.py): no AI, nothing is
   rewritten after the approval.
3. APPROVAL: bound to the version of the template, the zone, the offer, the sender and a volume. It starts the campaign
   that was approved, not an unlimited send: caps, windows, suppression, replies and every other gate still apply at the
   moment each message leaves (services/campaign_launch.py, services/journey_gate.py).

Nothing here sends a message: approving writes drafts and a plan; the scheduled task sends them one by one.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Campaign, CampaignApproval, Lead
from repositories import (
    audit_repo,
    draft_job_repo,
    draft_repo,
    journey_repo,
    launch_repo,
    outbound_repo,
    prospect_repo,
    send_policy_repo,
)
from services import campaign_launch, feature_flags, imap_svc, journey_gate, send_gate
from services.outreach_os import ai_draft, campaign_plan, campaign_template, drafts, email_footer
from services.outreach_os import heat as heat_rules
from services.outreach_os import provider_policy
from services.outreach_os import sandbox as sandbox_rules
from services.outreach_os.types import SignalState
from services.outreach_os.unsubscribe import make_token

ZONE_MAX_SPAN = 1.0  # degrees: roughly a large city and its surroundings; a country is not a zone
MAX_VOLUME = campaign_launch.MAX_SIZE
APPROVAL_VALID_DAYS = 14


class JourneyRefused(Exception):
    """The step cannot be done now; `code` says why and `label` says what to do."""

    def __init__(self, code: str, label: str) -> None:
        super().__init__(label)
        self.code, self.label = code, label


class ViewChanged(Exception):
    """What the person saw is no longer what would be approved: they must read the new summary first."""

    def __init__(self, code: str, actual: Optional[int] = None) -> None:
        super().__init__(code)
        self.code, self.actual = code, actual


# ---------------------------------------------------------------------------------------------- zone
def validate_zone(raw: dict[str, Any]) -> dict[str, Any]:
    """A usable perimeter: ordered coordinates inside the globe, not larger than ZONE_MAX_SPAN degrees."""
    try:
        south, west, north, east = (float(raw[k]) for k in ("south", "west", "north", "east"))
    except (KeyError, TypeError, ValueError):
        raise JourneyRefused("zone_invalid", "La zone doit être un rectangle sur la carte (sud, ouest, nord, est).")
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise JourneyRefused("zone_invalid", "Les coordonnées de la zone sont incohérentes.")
    if north - south > ZONE_MAX_SPAN or east - west > ZONE_MAX_SPAN:
        raise JourneyRefused(
            "zone_too_large",
            f"La zone est trop large (plus de {ZONE_MAX_SPAN:g}°) : choisissez une commune et un rayon.",
        )
    category = str(raw.get("category") or "").strip()[:40]
    if not category:
        raise JourneyRefused("zone_invalid", "Choisissez le type d'établissements de la zone.")
    return {
        "kind": "bbox",
        "south": south,
        "west": west,
        "north": north,
        "east": east,
        "category": category,
        "label": str(raw.get("label") or "").strip()[:80] or None,
    }


async def coverage(session: AsyncSession, account_id: uuid.UUID, zone: dict[str, Any]) -> dict[str, Any]:
    """What the sources really looked at for this perimeter. Never "all the establishments": a count and its limits."""
    job = await journey_repo.coverage_job(session, account_id, zone)
    if job is None:
        return {
            "searched": False,
            "statement": "Aucune recherche terminée ne couvre cette zone : lancez la recherche sur la carte.",
        }
    note = (
        "La recherche a atteint son plafond : la zone contient probablement d'autres établissements. "
        "Réduisez la zone pour les voir."
        if job.truncated
        else "Les résultats viennent des sources interrogées ; aucune source n'est exhaustive."
    )
    return {
        "searched": True,
        "places_found": job.result_count,
        "truncated": job.truncated,
        "source": job.source,
        "finished_at": job.finished_at,
        "statement": (
            f"{job.result_count} établissement(s) trouvé(s) par la recherche du {job.finished_at:%d/%m/%Y}. {note}"
            if job.finished_at
            else note
        ),
    }


# ---------------------------------------------------------------------------------------------- readiness (onboarding)
async def readiness(
    session: AsyncSession, account_id: uuid.UUID, scheduler: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """What must be configured ONCE, as a short checklist: each blocker says exactly what to do and where. The
    campaign never asks for these again; a warning does not block, it informs."""
    offer = ai_draft.valid_offer(await draft_job_repo.offer_of(session, account_id))
    sender = drafts.SenderIdentity.from_env()
    provider = campaign_launch.provider_info()
    items: list[dict[str, Any]] = [
        {
            "id": "offer",
            "ok": offer is not None,
            "blocking": True,
            "label": "Offre décrite" if offer else "Offre à décrire",
            "fix": (
                None if offer else "Pilotage › Offre : décrivez ce que vous vendez (nom, bénéfice, prochaine étape)."
            ),
            "link": "/app/settings/offer",
        },
        {
            "id": "identity",
            "ok": sender is not None,
            "blocking": True,
            "label": "Identité d'expéditeur configurée" if sender else "Identité d'expéditeur manquante",
            "fix": (
                None
                if sender
                else "Variables du serveur : OUTREACH_SENDER_NAME, OUTREACH_SENDER_COMPANY, OUTREACH_SENDER_ADDRESS, "
                "OUTREACH_SENDER_EMAIL (adresse postale réelle exigée)."
            ),
            "link": "/app/settings",
        },
        {
            "id": "provider",
            "ok": provider.cold_outreach != provider_policy.NOT_CONFIGURED,
            "blocking": True,
            "label": f"Fournisseur : {provider.label}",
            "fix": (
                None
                if provider.cold_outreach != provider_policy.NOT_CONFIGURED
                else "Pilotage › Intégrations : configurez SMTP (SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD)."
            ),
            "link": "/app/settings",
            "note": provider.restriction,
        },
    ]
    imap_ok = imap_svc.is_configured()
    items.append(
        {
            "id": "replies",
            "ok": imap_ok,
            "blocking": False,
            "label": "Réponses et oppositions lues (IMAP)" if imap_ok else "Réponses non lues : IMAP non configuré",
            "fix": (
                None
                if imap_ok
                else "Sans IMAP, une réponse ou une opposition reçue par e-mail n'arrête pas les envois suivants. "
                "Configurez IMAP_HOST, IMAP_USERNAME, IMAP_PASSWORD."
            ),
            "link": "/app/settings",
        }
    )
    worker_ok = bool(scheduler and scheduler.get("worker_ok") and scheduler.get("beat_ok"))
    items.append(
        {
            "id": "worker",
            "ok": worker_ok,
            "blocking": False,
            "label": "Worker et planificateur détectés" if worker_ok else "Worker ou planificateur non détecté",
            "fix": (
                None
                if worker_ok
                else "Le plan serait écrit mais aucun message ne partirait : démarrez un worker Celery et son beat "
                "(ou EMBEDDED_WORKER=1)."
            ),
            "link": "/app/system",
        }
    )
    live = not feature_flags.dry_run()
    code, sentence = sandbox_rules.scope(
        live=live, sandbox_on=feature_flags.sandbox(), entries=len(feature_flags.live_allowlist())
    )
    items.append(
        {
            "id": "mode",
            "ok": True,
            "blocking": False,
            "label": "Envoi réel" if live else "Simulation (rien ne part)",
            "fix": None,
            "note": sentence,
            "code": code,
        }
    )
    return {
        "ready": all(i["ok"] for i in items if i["blocking"]),
        "items": items,
        "blockers": [i for i in items if i["blocking"] and not i["ok"]],
    }


# ---------------------------------------------------------------------------------------------- rendering one message
@dataclass
class Material:
    lead: Lead
    rendered: campaign_template.Rendered
    source_name: Optional[str]


def _public_base_url() -> str:
    return os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")


async def _context(
    session: AsyncSession, lead: Lead, offer: dict[str, str], sender: drafts.SenderIdentity
) -> tuple[campaign_template.RenderContext, Optional[str]]:
    sources = await prospect_repo.sources_of(session, lead.id)
    latest = max(sources, key=lambda s: s.fetched_at) if sources else None
    results = await prospect_repo.effective_results(session, lead.id)  # a dismissed signal is never stated
    raw = (latest.fields.get("last_updated") if latest else None) or None
    updated = date.fromisoformat(raw) if isinstance(raw, str) else None
    pairs = drafts.observed_facts(results, latest.source_name if latest else "", updated)
    detected = {r.key: r.evidence for r in results if r.state is SignalState.DETECTED}
    state = ai_draft.site_state(website=lead.website if heat_rules.is_known(lead.website) else None, detected=detected)
    ctx = campaign_template.RenderContext(
        nom=lead.full_name,
        activite=lead.vertical,
        ville=lead.city,
        site_state=state,
        facts=pairs,
        offre=offer["name"],
        pitch=offer["pitch"],
        cta=offer["cta"],
        expediteur=f"{sender.name} — {sender.company}",
        language=offer["language"],
    )
    return ctx, (latest.source_name if latest else None)


async def render_for(
    session: AsyncSession, lead: Lead, template_subject: str, template_body: str, offer: dict[str, str], sender: Any
) -> Material:
    ctx, source_name = await _context(session, lead, offer, sender)
    return Material(lead, campaign_template.render(template_subject, template_body, ctx), source_name)


# ---------------------------------------------------------------------------------------------- creation and edition
async def create(
    session: AsyncSession,
    account_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    *,
    name: str,
    zone: dict[str, Any],
    size: int,
    now: datetime,
) -> tuple[Campaign, campaign_launch.Selection]:
    """The campaign of a zone, with its candidates and a first template pre-filled from the offer. Nothing is sent or
    approved. Refused, with what to do, while the offer is not described."""
    offer = ai_draft.valid_offer(await draft_job_repo.offer_of(session, account_id))
    if offer is None:
        raise JourneyRefused("offer_missing", "Décrivez d'abord votre offre (Pilotage › Offre) : le modèle part de là.")
    clean = validate_zone(zone)
    campaign, selection = await campaign_launch.create_launch(
        session, account_id, user_id, name=name, size=min(size, MAX_VOLUME), now=now, zone=clean
    )
    subject, body = campaign_template.default_template(offer)
    await journey_repo.add_template(
        session,
        account_id,
        campaign.id,
        subject=subject,
        body=body,
        content_hash=campaign_template.content_hash(subject, body),
        offer_hash=campaign_template.offer_hash(offer),
        user_id=user_id,
    )
    await audit_repo.log(
        session,
        account_id,
        action="journey.created",
        resource_type="campaign",
        resource_id=campaign.id,
        actor_user_id=user_id,
        diff={"selected": len(selection.picked), "category": clean["category"]},
    )
    return campaign, selection


async def edit_template(
    session: AsyncSession,
    account_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    campaign: Campaign,
    *,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """Save the template the person edited. A change of wording is a new version, and the approval no longer covers it;
    a change of spacing only is not a change. The previous versions stay as they were."""
    found = campaign_template.problems(subject, body)
    if found:
        raise JourneyRefused(found[0].code, "; ".join(p.label for p in found))
    latest = await journey_repo.latest_template(session, account_id, campaign.id)
    digest = campaign_template.content_hash(subject, body)
    if latest is not None and latest.content_hash == digest:
        return {"version": latest.version, "changed": False}
    offer = ai_draft.valid_offer(await draft_job_repo.offer_of(session, account_id))
    row = await journey_repo.add_template(
        session,
        account_id,
        campaign.id,
        subject=subject.strip(),
        body=body.strip(),
        content_hash=digest,
        offer_hash=campaign_template.offer_hash(offer),
        user_id=user_id,
    )
    await audit_repo.log(
        session,
        account_id,
        action="journey.template_edited",
        resource_type="campaign",
        resource_id=campaign.id,
        actor_user_id=user_id,
        diff={"version": row.version},
    )
    return {"version": row.version, "changed": True}


# ---------------------------------------------------------------------------------------------- the summary
@dataclass
class Audience:
    states: list[campaign_launch.LeadState]
    sendable: list[Material]  # eligible and rendered without a problem
    unrenderable: list[tuple[Lead, list[campaign_plan.Problem]]]


async def audience(
    session: AsyncSession, account_id: uuid.UUID, campaign: Campaign, now: datetime, subject: str, body: str
) -> Audience:
    """Who would receive the template: the live exclusions first (the same ones as every other campaign), then the
    rendering of each remaining establishment. A lead whose message cannot be written without a hole is held back."""
    states = await campaign_launch.evaluate(session, account_id, campaign, now)
    offer = ai_draft.valid_offer(await draft_job_repo.offer_of(session, account_id))
    sender = drafts.SenderIdentity.from_env()
    sendable: list[Material] = []
    unrenderable: list[tuple[Lead, list[campaign_plan.Problem]]] = []
    if offer is None or sender is None:
        return Audience(states, sendable, unrenderable)
    for state in states:
        if state.lead is None or state.exclusion or state.stage == "launched":
            continue
        material = await render_for(session, state.lead, subject, body, offer, sender)
        if material.rendered.problems:
            unrenderable.append((state.lead, material.rendered.problems))
        else:
            sendable.append(material)
    return Audience(states, sendable, unrenderable)


def pick_examples(sendable: list[Material], count: int = 3) -> list[Material]:
    """A few representative messages: one per website state when there is a choice, then the first ones."""
    chosen: list[Material] = []
    seen: set[str] = set()
    for material in sendable:
        if material.rendered.site_state not in seen:
            chosen.append(material)
            seen.add(material.rendered.site_state)
    for material in sendable:
        if len(chosen) >= count:
            break
        if material not in chosen:
            chosen.append(material)
    return chosen[:count]


async def _slots(
    session: AsyncSession, account_id: uuid.UUID, campaign: Campaign, leads: list[Lead], now: datetime
) -> tuple[dict[str, Any], Any]:
    policy = await send_policy_repo.get_policy(session, account_id, "email")
    slot_policy = campaign_launch._slot_policy(policy)
    day_start, _ = send_gate.day_bounds(now, slot_policy.timezone)
    sent = await outbound_repo.dispatch_times_since(session, account_id, "email", day_start)
    taken = await launch_repo.planned_times(session, account_id)
    windows = [campaign_launch.zone_name(lead, policy) for lead in leads]
    slots = campaign_plan.plan_slots(
        len(leads), now=now, policy=slot_policy, already_sent=sent + taken, windows=windows
    )
    return campaign_plan.schedule_summary(slots, slot_policy.timezone), policy


async def summary(
    session: AsyncSession, account_id: uuid.UUID, campaign: Campaign, now: datetime, scheduler: Optional[dict[str, Any]]
) -> dict[str, Any]:
    """Everything the approval screen shows, computed from the data as it is now."""
    assert campaign.zone is not None
    template = await journey_repo.latest_template(session, account_id, campaign.id)
    if template is None:  # a campaign created before its template existed: nothing to approve yet
        raise JourneyRefused("template_missing", "Ce parcours n'a pas encore de modèle.")
    ready = await readiness(session, account_id, scheduler)
    aud = await audience(session, account_id, campaign, now, template.subject, template.body)
    approval, why = await journey_gate.reasons(session, campaign, now)
    exclusions = campaign_launch.exclusion_counts(aud.states)
    offer = ai_draft.valid_offer(await draft_job_repo.offer_of(session, account_id))
    sender = drafts.SenderIdentity.from_env()
    schedule, policy = await _slots(session, account_id, campaign, [m.lead for m in aud.sendable], now)
    problems = campaign_template.problems(template.subject, template.body)
    launched = sum(1 for s in aud.states if s.stage == "launched")
    return {
        "campaign": {"id": str(campaign.id), "name": campaign.name, "status": campaign.status},
        "zone": campaign.zone,
        "coverage": await coverage(session, account_id, campaign.zone),
        "readiness": ready,
        "audience": {
            "selected": len(aud.states),
            "sendable": len(aud.sendable),
            "already_sent": launched,
            "held_back": [
                {"lead_id": str(lead.id), "name": lead.full_name, "problems": [p.label for p in found]}
                for lead, found in aud.unrenderable[:20]
            ],
            "held_back_count": len(aud.unrenderable),
            "exclusions": exclusions,
            "exclusion_labels": {code: campaign_plan.exclusion_label(code) for code in exclusions},
        },
        "template": {
            "version": template.version,
            "subject": template.subject,
            "body": template.body,
            "content_hash": template.content_hash,
            "problems": [{"code": p.code, "label": p.label} for p in problems],
            "placeholders": list(campaign_template.PLACEHOLDERS),
            "footer_note": "Le pied du message (identité, origine des données, lien de désinscription) est ajouté "
            "par le serveur à chaque message : il n'est pas modifiable.",
        },
        "examples": [
            {
                "name": m.lead.full_name,
                "city": m.lead.city,
                "email": m.lead.email,
                "subject": m.rendered.subject,
                "body": m.rendered.body,
                "facts": m.rendered.facts,
                "site_state": m.rendered.site_state,
            }
            for m in pick_examples(aud.sendable)
        ],
        "volume": {
            "messages": len(aud.sendable),
            "daily_cap": policy.max_per_day,
            "total_cap": min(len(aud.sendable), MAX_VOLUME),
        },
        "sender": {
            "configured": sender is not None,
            "name": sender.name if sender else None,
            "company": sender.company if sender else None,
            "email": sender.reply_to if sender else None,
            "provider": campaign_launch.provider_info().label,
        },
        "schedule": schedule,
        "approval": {
            "approved": approval is not None,
            "valid": approval is not None and not why,
            "reasons": [{"code": c, "label": campaign_template.reason_label(c)} for c in why],
            "template_version": approval.template_version if approval else None,
            "approved_at": approval.created_at if approval else None,
            "expires_at": approval.expires_at if approval else None,
            "revoked_at": approval.revoked_at if approval else None,
            "mandate_id": str(approval.mandate_id) if approval and approval.mandate_id else None,
        },
        "offer_configured": offer is not None,
        "generated_at": now,
    }


# ---------------------------------------------------------------------------------------------- approval
def _footer(account_id: uuid.UUID, lead: Lead, sender: drafts.SenderIdentity, source_name: Optional[str]) -> str:
    from deps import JWT_SECRET  # the unsubscribe link is signed with the same secret as everywhere else

    return email_footer.render_footer(
        name=sender.name,
        company=sender.company,
        postal_address=sender.postal_address,
        source=f"annuaire « {source_name} »" if source_name else None,
        unsubscribe_url=f"{_public_base_url()}/api/unsubscribe/{make_token(JWT_SECRET, account_id, lead.id)}",
        reply_to=sender.reply_to,
        whatsapp=sender.whatsapp,
    )


async def _materialize(
    session: AsyncSession,
    account_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    campaign: Campaign,
    version: int,
    material: Material,
    sender: drafts.SenderIdentity,
    now: datetime,
) -> bool:
    """Write the approved draft of one recipient (idempotent per campaign, version and prospect). False = not written:
    the message would not pass the compliance check."""
    body = f"{material.rendered.body}\n\n{_footer(account_id, material.lead, sender, material.source_name)}"
    if drafts.compliance_problems(body, sender):
        return False
    draft, created = await draft_repo.create_idempotent(
        session,
        account_id,
        idempotency_key=f"journey:{campaign.id}:{version}:{material.lead.id}",
        lead_id=material.lead.id,
        channel="email",
        subject=material.rendered.subject,
        body=body,
        facts=list(material.rendered.facts),
        template_version=f"journey-{version}",
        status="approved",
        dry_run=feature_flags.dry_run(),
        created_by_user_id=user_id,
        reviewed_by_user_id=user_id,
        reviewed_at=now,
        review_note=f"Approuvé avec la campagne (modèle v{version})",
    )
    return True


async def approve(
    session: AsyncSession,
    account_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    campaign: Campaign,
    *,
    expected_hash: str,
    expected_count: int,
    now: datetime,
    scheduler: Optional[dict[str, Any]] = None,
    mandate_id: Optional[uuid.UUID] = None,
    daily_cap: Optional[int] = None,
    total_cap: Optional[int] = None,
    valid_until: Optional[datetime] = None,
) -> dict[str, Any]:
    """Approve the campaign as the person saw it, then write its drafts and its plan. Refused (nothing written) when
    something that blocks is not configured, when the template is not the one that was shown, or when the number of
    messages is no longer the one that was shown."""
    ready = await readiness(session, account_id, scheduler)
    if ready["blockers"]:
        first = ready["blockers"][0]
        raise JourneyRefused(f"not_ready_{first['id']}", first["fix"] or first["label"])
    template = await journey_repo.latest_template(session, account_id, campaign.id)
    if template is None:
        raise JourneyRefused("template_missing", "Ce parcours n'a pas de modèle.")
    if template.content_hash != expected_hash:
        raise ViewChanged("template_changed")
    found = campaign_template.problems(template.subject, template.body)
    if found:
        raise JourneyRefused(found[0].code, "; ".join(p.label for p in found))
    aud = await audience(session, account_id, campaign, now, template.subject, template.body)
    if len(aud.sendable) != expected_count:
        raise ViewChanged("audience_changed", len(aud.sendable))
    if not aud.sendable:
        raise JourneyRefused("nothing_to_send", "Aucun établissement ne peut recevoir ce message : rien à approuver.")
    sender = drafts.SenderIdentity.from_env()
    offer = ai_draft.valid_offer(await draft_job_repo.offer_of(session, account_id))
    assert sender is not None and offer is not None and campaign.zone is not None
    policy = await send_policy_repo.get_policy(session, account_id, "email")
    approval = await journey_repo.add_approval(
        session,
        CampaignApproval(
            account_id=account_id,
            campaign_id=campaign.id,
            template_version=template.version,
            content_hash=template.content_hash,
            zone_hash=campaign_template.zone_hash(campaign.zone),
            offer_hash=campaign_template.offer_hash(offer),
            sender_fp=journey_gate.sender_fp(),
            audience_count=len(aud.sendable),
            daily_cap=daily_cap if daily_cap is not None else policy.max_per_day,
            total_cap=total_cap if total_cap is not None else min(len(aud.sendable), MAX_VOLUME),
            approved_by_user_id=user_id,
            mandate_id=mandate_id,
            expires_at=valid_until or now + timedelta(days=APPROVAL_VALID_DAYS),
        ),
    )
    # Messages planned under an earlier approval are planned again from the new drafts: an old plan never sends the
    # old wording under the new approval.
    await launch_repo.cancel_scheduled(session, account_id, campaign.id, now)
    written = 0
    for material in aud.sendable:
        if await _materialize(session, account_id, user_id, campaign, template.version, material, sender, now):
            written += 1
    states = await campaign_launch.evaluate(session, account_id, campaign, now)
    ready_states = [s for s in states if s.sendable]
    result = await campaign_launch.schedule(session, account_id, user_id, campaign, expected=len(ready_states), now=now)
    await audit_repo.log(
        session,
        account_id,
        action="journey.approved",
        resource_type="campaign",
        resource_id=campaign.id,
        actor_user_id=user_id,
        diff={
            "template_version": template.version,
            "messages": written,
            "scheduled": result.get("scheduled", 0),
            "mandate": str(mandate_id) if mandate_id else None,
        },
    )
    return {
        "approval_id": str(approval.id),
        "template_version": template.version,
        "drafts": written,
        "scheduled": result.get("scheduled", 0),
        "refused": result.get("refused"),
        "first_at": result["schedule"]["first_at"],
        "last_at": result["schedule"]["last_at"],
    }


async def revoke(
    session: AsyncSession,
    account_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    campaign: Campaign,
    *,
    reason: Optional[str],
    now: datetime,
) -> dict[str, Any]:
    """Withdraw the approval: nothing that has not left will leave. What already left cannot be recalled."""
    approval = await journey_repo.latest_approval(session, account_id, campaign.id)
    if approval is None or approval.revoked_at is not None:
        raise JourneyRefused("not_approved", "Aucune approbation en vigueur à révoquer.")
    approval.revoked_at = now
    approval.revoked_by_user_id = user_id
    approval.revoke_reason = (reason or "").strip()[:200] or None
    cancelled = await launch_repo.cancel_scheduled(session, account_id, campaign.id, now)
    campaign.status = "paused"
    await audit_repo.log(
        session,
        account_id,
        action="journey.revoked",
        resource_type="campaign",
        resource_id=campaign.id,
        actor_user_id=user_id,
        diff={"cancelled": cancelled},
    )
    return {"cancelled": cancelled, "status": campaign.status}


async def pause(
    session: AsyncSession, account_id: uuid.UUID, user_id: Optional[uuid.UUID], campaign: Campaign, *, paused: bool
) -> dict[str, Any]:
    """Pause: planned messages wait where they are (nothing is cancelled) and leave again on resume. Resuming is only
    possible while an approval still covers the campaign."""
    if not paused:
        _, why = await journey_gate.reasons(session, campaign, datetime.now(timezone.utc))
        if why:
            raise JourneyRefused(why[0], campaign_template.reason_label(why[0]))
    campaign.status = "paused" if paused else "running"
    await audit_repo.log(
        session,
        account_id,
        action="journey.paused" if paused else "journey.resumed",
        resource_type="campaign",
        resource_id=campaign.id,
        actor_user_id=user_id,
        diff={},
    )
    return {"status": campaign.status}


# ---------------------------------------------------------------------------------------------- the compact dashboard
REPLY_STATES = ("replied", "opted_out", "bounced")


async def progress(session: AsyncSession, account_id: uuid.UUID, campaign: Campaign, now: datetime) -> dict[str, Any]:
    """What the main table shows: progression, what needs the person, replies and the pause control."""
    counts, _, _ = await campaign_launch.tracking(session, account_id, campaign, state=None, offset=0, limit=0)
    total = sum(counts.values())
    done_states = (
        "accepted",
        "simulated",
        "replied",
        "opted_out",
        "bounced",
        "failed",
        "unknown",
        "skipped",
        "cancelled",
    )
    done = sum(counts.get(s, 0) for s in done_states)
    approval, why = await journey_gate.reasons(session, campaign, now)
    actions: list[dict[str, Any]] = []
    if counts.get("unknown"):
        actions.append(
            {
                "code": "unknown_outcome",
                "count": counts["unknown"],
                "label": "Résultat inconnu : vérifiez la boîte d'envoi (jamais renvoyés d'eux-mêmes).",
            }
        )
    if approval is not None and why:
        actions.append({"code": "approval_stale", "count": 1, "label": campaign_template.reason_label(why[0])})
    if counts.get("failed"):
        actions.append(
            {"code": "failed", "count": counts["failed"], "label": "Envois refusés par le serveur de messagerie."}
        )
    plans = await launch_repo.dispatches_of(session, account_id, campaign.id)
    stopped: dict[str, int] = {}
    for row in plans.values():
        if row.status == "skipped" and row.last_reason:
            stopped[row.last_reason] = stopped.get(row.last_reason, 0) + 1
    for code, n in sorted(stopped.items(), key=lambda kv: -kv[1]):
        actions.append({"code": code, "count": n, "label": campaign_plan.exclusion_label(code)})
    return {
        "status": campaign.status,
        "paused": campaign.status == "paused",
        "total": total,
        "done": done,
        "percent": round(100 * done / total) if total else None,
        "states": counts,
        "replies": {s: counts.get(s, 0) for s in REPLY_STATES},
        "actions": actions,
        "approval_valid": approval is not None and not why,
    }


async def journeys(session: AsyncSession, account_id: uuid.UUID) -> list[dict[str, Any]]:
    out = []
    for campaign in await journey_repo.journeys(session, account_id):
        counts = await launch_repo.counts(session, account_id, campaign.id)
        recipients = len(await launch_repo.selection_of(session, account_id, campaign.id))
        out.append(
            {
                "id": str(campaign.id),
                "name": campaign.name,
                "status": campaign.status,
                "zone": campaign.zone,
                "recipients": recipients,
                "planned": counts.get("scheduled", 0) + counts.get("sending", 0),
                "sent": counts.get("accepted", 0),
                "created_at": campaign.created_at,
            }
        )
    return out
