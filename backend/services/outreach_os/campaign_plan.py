"""The pure rules of an individual campaign: who is excluded and why, what blocks a draft in the review, when each
message may leave, and how a message is reported. No I/O, no clock (always injected).

Nothing here sends anything. A campaign of individual messages is one prepared draft per recipient, approved by a
person, planned one by one inside the send window and the limits; every gate is checked again at the moment each
message would actually leave (services/campaign_launch.py), by the same code every other send path uses.
"""

from __future__ import annotations

import re
import zoneinfo
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

# ---------------------------------------------------------------------------------------------- exclusions
# Why a prospect is not part of the campaign (selection) or not sendable (plan, send time). Stable codes, French labels.
EXCLUSIONS: dict[str, str] = {
    "not_approved": "Prospect non validé (file « À vérifier »)",
    "not_qualified": "Prospect non qualifié (coordonnées, adresse, position ou score insuffisants)",
    "no_email": "Aucune adresse e-mail publiée",
    "invalid_email": "Adresse e-mail invalide ou réservée",
    "suppressed": "Sur la liste de suppression (opposition, effacement, rebond ou ajout manuel)",
    "opted_out": "S'est opposé aux e-mails",
    "bounced": "Un message précédent a rebondi (adresse morte)",
    "already_replied": "A déjà répondu",
    "already_contacted": "Un message lui a déjà été envoyé ou est en cours d'envoi",
    "campaign_conflict": "Déjà dans une autre campagne active ou planifiée",
    "duplicate_email": "Même adresse e-mail qu'un autre destinataire (un seul message par adresse)",
    "duplicate_establishment": "Même établissement (nom et ville) qu'un autre destinataire",
    "provider_requires_opt_in": "Pas d'opt-in : non autorisé à recevoir une campagne via ce fournisseur",
    "demo": "Donnée de démonstration",
    "rejected": "Prospect rejeté",
}

# Why a planned message was refused when it was about to leave. "wait" = come back later, "stop" = never sent.
SEND_REFUSALS: dict[str, tuple[str, str]] = {
    "kill_switch": ("wait", "Arrêt d'urgence actif (SEND_KILL_SWITCH)"),
    "paused": ("wait", "Envois en pause pour l'organisation"),
    "campaign_paused": ("wait", "Campagne en pause"),
    "limit_daily": ("wait", "Limite quotidienne atteinte"),
    "limit_hourly": ("wait", "Limite horaire atteinte"),
    "limit_delay": ("wait", "Délai minimal entre deux messages"),
    "outside_window": ("wait", "Hors de la fenêtre d'envoi"),
    "live_not_available": ("wait", "Envoi réel activé sans configuration SMTP complète"),
    "sender_not_configured": ("wait", "Identité de l'expéditeur non configurée"),
    "draft_not_approved": ("stop", "Brouillon non approuvé (modifié depuis ?)"),
    "prospect_gone": ("stop", "Prospect supprimé"),
    "prospect_not_approved": ("stop", "Prospect plus validé"),
    "recipient_changed": ("stop", "L'adresse du prospect a changé depuis la planification"),
    "no_email": ("stop", EXCLUSIONS["no_email"]),
    "suppressed": ("stop", EXCLUSIONS["suppressed"]),
    "opted_out": ("stop", EXCLUSIONS["opted_out"]),
    "bounced": ("stop", EXCLUSIONS["bounced"]),
    "already_replied": ("stop", EXCLUSIONS["already_replied"]),
    "campaign_conflict": ("stop", EXCLUSIONS["campaign_conflict"]),
    "provider_requires_opt_in": ("stop", EXCLUSIONS["provider_requires_opt_in"]),
    "sandbox_recipient": ("stop", "Bac à sable actif : destinataire absent de OUTREACH_LIVE_ALLOWLIST"),
    "not_compliant": ("stop", "Brouillon non conforme (identité, origine des données ou désinscription)"),
    "campaign_gone": ("stop", "Campagne supprimée"),
    # a campaign with a zone sends only what its approval still covers (services/journey_gate.py)
    "not_approved": ("stop", "Campagne non approuvée"),
    "revoked": ("stop", "Approbation révoquée"),
    "expired": ("stop", "Approbation expirée"),
    "template_changed": ("stop", "Le modèle a changé depuis l'approbation : approuvez de nouveau"),
    "zone_changed": ("stop", "La zone a changé depuis l'approbation : approuvez de nouveau"),
    "offer_changed": ("stop", "L'offre a changé depuis l'approbation : approuvez de nouveau"),
    "sender_changed": ("stop", "L'expéditeur a changé depuis l'approbation : approuvez de nouveau"),
    "cap_total": ("stop", "Plafond total de l'approbation atteint"),
    "cap_daily": ("wait", "Plafond quotidien de l'approbation atteint"),
    "mandate_inactive": ("stop", "Le mandat d'automatisation n'est plus actif"),
    "mandate_cap": ("stop", "Plafond du mandat atteint"),
}


def exclusion_label(code: str) -> str:
    return EXCLUSIONS.get(code) or SEND_REFUSALS.get(code, ("stop", code))[1]


def refusal_kind(code: str) -> str:
    """ "wait" when time can fix it, "stop" when the message must not leave (unknown codes stop: fail closed)."""
    return SEND_REFUSALS.get(code, ("stop", ""))[0]


def establishment_key(name: str, city: Optional[str]) -> str:
    """Two prospects with the same folded name in the same city are one establishment."""
    from services.outreach_os.normalize import normalize_name

    return f"{normalize_name(name or '')}|{normalize_name(city or '')}"


# ---------------------------------------------------------------------------------------------- review
_VARIABLES = re.compile(
    r"\{\{[^{}]*\}\}"  # {{name}}
    r"|\{[A-Za-z_][A-Za-z0-9_ .]*\}"  # {name}
    r"|%[A-Za-z_]+%"  # %NAME%
    r"|\[\[[^\[\]]*\]\]"  # [[name]]
    r"|<<[^<>]*>>"  # <<name>>
    r"|\[(?:nom|name|prénom|prenom|ville|city|entreprise|company|site|société|societe|établissement|etablissement)\]",
    re.IGNORECASE,
)


def unresolved_variables(*texts: str) -> list[str]:
    """Template variables left in a message ("{{name}}", "[Ville]"…): a message with one must never leave."""
    found: list[str] = []
    for text in texts:
        for match in _VARIABLES.finditer(text or ""):
            if match.group(0) not in found:
                found.append(match.group(0))
    return found


@dataclass(frozen=True)
class Problem:
    code: str
    label: str
    blocking: bool = True


@dataclass(frozen=True)
class ReviewInput:
    subject: str
    body: str
    facts: Sequence[str]  # the observations the draft states, as stored with it
    sourced_now: Sequence[str]  # the observations a detected, not-dismissed signal backs today
    compliance: Sequence[str]  # drafts.compliance_problems(...)
    sender_configured: bool
    edited_by_hand: bool = False


def review_problems(item: ReviewInput) -> list[Problem]:
    """What stops a draft from being scheduled, and what the reviewer should simply know. Nothing here is a guess: a
    statement is "unsourced" when no detected signal backs it any more (dismissed or no longer observed)."""
    out: list[Problem] = []
    if not item.subject.strip():
        out.append(Problem("empty_subject", "Objet vide"))
    if not item.body.strip():
        out.append(Problem("empty_body", "Corps vide"))
    variables = unresolved_variables(item.subject, item.body)
    if variables:
        out.append(Problem("unresolved_variable", "Variable non résolue : " + ", ".join(variables)))
    unsourced = [fact for fact in item.facts if fact not in set(item.sourced_now)]
    if unsourced:
        out.append(
            Problem(
                "unsourced_fact",
                "Constat sans source actuelle : « " + " » ; « ".join(unsourced) + " » (signal écarté ou plus observé)",
            )
        )
    if not item.sender_configured:
        out.append(Problem("sender_missing", "Identité de l'expéditeur non configurée"))
    elif item.compliance:
        out.append(Problem("not_compliant", "Non conforme : " + ", ".join(item.compliance)))
    if item.edited_by_hand:
        out.append(
            Problem(
                "edited_by_hand",
                "Texte modifié à la main : les affirmations ajoutées ne sont pas vérifiées, relisez-les",
                blocking=False,
            )
        )
    return out


def blocking(problems: Sequence[Problem]) -> list[Problem]:
    return [p for p in problems if p.blocking]


# ---------------------------------------------------------------------------------------------- schedule
@dataclass(frozen=True)
class SlotPolicy:
    max_per_day: int
    max_per_hour: int
    min_delay_seconds: int
    window_start_hour: int
    window_end_hour: int
    timezone: str


def _zone(name: str) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(name)
    except Exception:  # noqa: BLE001 (an unknown zone name falls back to UTC, like the send gate)
        return zoneinfo.ZoneInfo("UTC")


def next_window_start(local: datetime, start_hour: int) -> datetime:
    """The next time the send window opens, strictly after `local` (a timezone-aware local time)."""
    candidate = local.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    return candidate if candidate > local else candidate + timedelta(days=1)


MAX_STEPS = 100_000


def plan_slots(
    count: int,
    *,
    now: datetime,
    policy: SlotPolicy,
    already_sent: Sequence[datetime],
    windows: Optional[Sequence[str]] = None,
) -> list[datetime]:
    """The earliest time each of `count` messages may leave, one after the other, never outside the send window, never
    over the daily cap, the rolling hourly cap or the minimum delay, counting what already left (`already_sent`, any
    path).

    `windows` names, message by message, the time zone whose send window applies to that recipient (the executor reads
    the window in the recipient's own zone when the policy asks for it); without it, or past its end, the window is read
    in the organisation's zone. The daily cap always counts local days of the organisation's zone, like the send gate.

    These are "not before" times: at the moment a message really leaves, the same limits are checked again against
    what really happened. Returns fewer than `count` slots only when the policy allows none (a cap of 0, an empty
    window)."""
    if count <= 0 or policy.max_per_day <= 0 or policy.max_per_hour <= 0:
        return []
    if not 0 <= policy.window_start_hour < policy.window_end_hour <= 24:
        return []
    zone = _zone(policy.timezone)
    step = timedelta(seconds=max(policy.min_delay_seconds, 1))
    history = sorted(already_sent)
    planned: list[datetime] = []
    t = now.astimezone(timezone.utc)
    for _ in range(MAX_STEPS):
        if len(planned) >= count:
            break
        window_zone = _zone(windows[len(planned)]) if windows and len(planned) < len(windows) else zone
        local = t.astimezone(window_zone)
        if local.hour < policy.window_start_hour:
            t = local.replace(hour=policy.window_start_hour, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
            continue
        if local.hour >= policy.window_end_hour:
            t = next_window_start(local, policy.window_start_hour).astimezone(timezone.utc)
            continue
        every = history + planned
        day = t.astimezone(zone).date()
        if sum(1 for x in every if x.astimezone(zone).date() == day) >= policy.max_per_day:
            following = day + timedelta(days=1)
            t = datetime(following.year, following.month, following.day, tzinfo=zone).astimezone(timezone.utc)
            continue
        recent = sorted(x for x in every if t - timedelta(hours=1) < x <= t)
        if len(recent) >= policy.max_per_hour:
            t = recent[len(recent) - policy.max_per_hour] + timedelta(hours=1)
            continue
        if every and t < max(every) + step:
            t = max(every) + step
            continue
        planned.append(t)
        t = t + step
    return planned


def schedule_summary(slots: Sequence[datetime], timezone_name: str) -> dict[str, Any]:
    """First and last send, and how many per local day: what the operator reads before pressing the button."""
    zone = _zone(timezone_name)
    days: dict[str, int] = {}
    for slot in slots:
        key = slot.astimezone(zone).date().isoformat()
        days[key] = days.get(key, 0) + 1
    return {
        "first_at": min(slots) if slots else None,
        "last_at": max(slots) if slots else None,
        "days": [{"date": d, "count": n} for d, n in sorted(days.items())],
        "timezone": timezone_name,
    }


# ---------------------------------------------------------------------------------------------- tracking
# What the operator sees for one recipient. "delivered" does not exist: the SMTP server accepting a message is not a
# proof that it reached an inbox, and nothing in the system observes a delivery.
TRACKING = (
    "scheduled",  # planifié
    "sending",  # en cours d'envoi
    "simulated",  # accepté par le simulateur (dry-run) : rien n'est parti
    "accepted",  # accepté par le serveur SMTP (pas une preuve de livraison)
    "replied",  # réponse reçue
    "opted_out",  # opposition (désinscription)
    "bounced",  # rebond
    "failed",  # refusé par le serveur : définitivement non envoyé
    "unknown",  # résultat inconnu : à vérifier dans la boîte d'envoi, jamais renvoyé
    "skipped",  # arrêté avant l'envoi (raison indiquée)
    "cancelled",  # annulé par un humain
)
TRACKING_LABELS = {
    "scheduled": "Planifié",
    "sending": "En cours d'envoi",
    "simulated": "Simulé (dry-run, rien n'est parti)",
    "accepted": "Accepté par SMTP (livraison non prouvée)",
    "replied": "Réponse reçue",
    "opted_out": "Opposition",
    "bounced": "Rebond",
    "failed": "Échec",
    "unknown": "Résultat inconnu : vérifier la boîte d'envoi",
    "skipped": "Arrêté avant l'envoi",
    "cancelled": "Annulé",
}


def tracking_state(
    *, dispatch_status: str, message_status: Optional[str], message_dry_run: Optional[bool], opted_out: bool
) -> str:
    """The one honest word for a recipient, from the plan row and (once it exists) the message of the send ledger."""
    if dispatch_status in ("scheduled", "sending", "failed", "unknown", "skipped", "cancelled"):
        return dispatch_status
    # dispatch_status == "accepted": the ledger says what happened next
    if opted_out:
        return "opted_out"
    if message_status == "bounced":
        return "bounced"
    if message_status == "replied":
        return "replied"
    if message_status == "failed":
        return "failed"
    if message_status == "sending":
        return "unknown"
    return "simulated" if message_dry_run else "accepted"
