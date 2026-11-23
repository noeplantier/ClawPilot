"""The rules of the bounded automatic mode ("Automatisation max"): pure, no I/O, `now` injected.

A mandate is ONE explicit authorisation, with its limits written down: a zone, a version of the message, a sender and a
provider, caps (per day, in total), a cadence, an expiry and the conditions that stop it. The automatic mode does only
what the mandate says and stops when it says so; it never widens a zone, an offer, an audience, a quota or a budget by
itself. What is uncertain is left out or handed back to a person.

This module decides three things, all testable without a database:
* is a mandate as written acceptable? (`problems`)
* may it act now, must it wait, or must it stop? (`verdict`)
* what does a recipient's message have to satisfy at the moment it would leave? (`send_refusal`)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from services.outreach_os import campaign_template

MAX_ZONES = 1  # one zone per mandate: a second zone is a second mandate, authorised on its own
MAX_DAILY = 100
MAX_TOTAL = (
    100  # a campaign holds at most 100 recipients: a bigger programme is a second, separately authorised mandate
)
MAX_DAYS = 90
MIN_DELAY_SECONDS = 30
MIN_SEARCH_HOURS = 6
DEFAULT_STOP_RULES: dict[str, Any] = {
    "max_bounce_rate": 0.05,  # suspend above 5 % hard bounces ...
    "max_opt_out_rate": 0.10,  # ... or 10 % oppositions ...
    "min_sample": 20,  # ... once at least 20 messages have gone out (a rate on 3 messages means nothing)
}
FIXED_STOPS = (  # not configurable: removing one would make the mode blind
    "kill_switch",
    "auth_error",
    "reply_collection_down",
    "needs_revalidation",
    "provider_changed",
    "expired",
    "cap_total",
)

STOP_LABELS = {
    "expired": "Le mandat a expiré",
    "kill_switch": "Arrêt d'urgence actif (SEND_KILL_SWITCH)",
    "auth_error": "Le serveur de messagerie refuse l'authentification : vérifiez les identifiants",
    "reply_collection_down": "Les réponses ne sont plus lues (IMAP indisponible) : une opposition passerait inaperçue",
    "bounce_rate": "Trop de rebonds : l'envoi est suspendu pour protéger la réputation de l'expéditeur",
    "opt_out_rate": "Trop d'oppositions : l'envoi est suspendu, relisez le message et la cible",
    "needs_revalidation": "Un paramètre substantiel a changé : revalidez le mandat",
    "provider_changed": "Le fournisseur d'envoi a changé depuis l'autorisation",
    "cap_total": "Le plafond total du mandat est atteint : il est terminé",
    "feature_disabled": "Le mode automatique est désactivé sur ce serveur (FEATURE_AUTOMATION_MAX)",
    "revoked": "Le mandat a été révoqué",
    "not_active": "Le mandat n'est pas actif",
}


@dataclass(frozen=True)
class Problem:
    code: str
    label: str


@dataclass(frozen=True)
class Spec:
    """A mandate as the person wrote it (before it is stored)."""

    zones: list[Mapping[str, Any]]
    daily_cap: int
    total_cap: int
    expires_at: datetime
    window_start_hour: int = 8
    window_end_hour: int = 18
    min_delay_seconds: int = 60
    search_every_hours: int = 24
    ai_budget: int = 0
    stop_rules: Mapping[str, Any] = field(default_factory=lambda: dict(DEFAULT_STOP_RULES))


def stop_rules_of(raw: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """The configurable rules, bounded and completed with the defaults (a rule can be stricter, never looser than the
    hard limits)."""
    merged = {**DEFAULT_STOP_RULES, **(raw or {})}
    return {
        "max_bounce_rate": min(max(float(merged["max_bounce_rate"]), 0.005), 0.10),
        "max_opt_out_rate": min(max(float(merged["max_opt_out_rate"]), 0.01), 0.20),
        "min_sample": min(max(int(merged["min_sample"]), 5), 200),
    }


def problems(spec: Spec, now: datetime) -> list[Problem]:
    """What makes a mandate unacceptable as written. Nothing is corrected silently."""
    out: list[Problem] = []
    if not spec.zones:
        out.append(Problem("zone_missing", "Un mandat porte sur une zone précise : choisissez-la."))
    if len(spec.zones) > MAX_ZONES:
        out.append(
            Problem("too_many_zones", "Un mandat couvre une seule zone ; une autre zone, c'est un autre mandat.")
        )
    if not 1 <= spec.daily_cap <= MAX_DAILY:
        out.append(Problem("daily_cap", f"Le plafond quotidien doit être compris entre 1 et {MAX_DAILY}."))
    if not 1 <= spec.total_cap <= MAX_TOTAL:
        out.append(Problem("total_cap", f"Le plafond total doit être compris entre 1 et {MAX_TOTAL}."))
    if spec.daily_cap > spec.total_cap:
        out.append(Problem("caps_order", "Le plafond quotidien ne peut pas dépasser le plafond total."))
    if spec.expires_at <= now:
        out.append(Problem("expiry_past", "La date d'expiration doit être dans le futur."))
    elif spec.expires_at > now + timedelta(days=MAX_DAYS):
        out.append(
            Problem("expiry_far", f"Un mandat dure {MAX_DAYS} jours au plus : il se renouvelle, il ne s'éternise pas.")
        )
    if not 0 <= spec.window_start_hour < spec.window_end_hour <= 24:
        out.append(Problem("window", "La fenêtre horaire est invalide."))
    if spec.min_delay_seconds < MIN_DELAY_SECONDS:
        out.append(Problem("cadence", f"Au moins {MIN_DELAY_SECONDS} secondes entre deux messages."))
    if spec.search_every_hours < MIN_SEARCH_HOURS:
        out.append(Problem("search_frequency", f"Une recherche au plus toutes les {MIN_SEARCH_HOURS} heures."))
    if spec.ai_budget < 0:
        out.append(Problem("ai_budget", "Le budget IA ne peut pas être négatif (0 = aucune génération IA)."))
    return out


@dataclass(frozen=True)
class Pinned:
    """What the mandate was authorised for."""

    content_hash: str
    zone_hash: Optional[str]
    offer_hash: Optional[str]
    sender_fp: Optional[str]
    provider: Optional[str]


@dataclass(frozen=True)
class Health:
    """What the system observes about the mandate right now (read once per run, never guessed)."""

    now: datetime
    kill_switch: bool
    feature_enabled: bool
    auth_error: bool
    reply_collection_ok: bool
    sent_total: int
    bounced: int
    opted_out: int
    current: campaign_template.Current
    provider: Optional[str]


@dataclass(frozen=True)
class Verdict:
    """`go`: act now. `hold`: do nothing this time, the cause is temporary or global. `suspend`: stop until a person
    looks (the mandate stays, nothing is sent). `end`: finished for good (expired, complete)."""

    action: str
    code: Optional[str] = None
    detail: Optional[str] = None

    @property
    def label(self) -> Optional[str]:
        return STOP_LABELS.get(self.code or "", self.code) if self.code else None


GO = Verdict("go")


def verdict(
    *,
    status: str,
    expires_at: datetime,
    total_cap: int,
    rules: Mapping[str, Any],
    pinned: Pinned,
    health: Health,
) -> Verdict:
    """May the mandate act now? The first reason found wins, in the order a person would check them."""
    if status in ("revoked", "expired"):
        return Verdict("end", status)
    if status != "active":
        return Verdict("hold", "not_active")
    if not health.feature_enabled:
        return Verdict("hold", "feature_disabled")
    if health.now >= expires_at:
        return Verdict("end", "expired")
    if health.kill_switch:
        return Verdict("hold", "kill_switch")
    if health.auth_error:
        return Verdict("suspend", "auth_error")
    if not health.reply_collection_ok:
        return Verdict("suspend", "reply_collection_down")
    changed = campaign_template.approval_reasons(
        campaign_template.Binding(
            pinned.content_hash, pinned.zone_hash, pinned.offer_hash, pinned.sender_fp, None, revoked=False
        ),
        health.current,
        health.now,
    )
    if changed:
        return Verdict("suspend", "needs_revalidation", ",".join(changed))
    if pinned.provider is not None and health.provider != pinned.provider:
        return Verdict("suspend", "provider_changed")
    rules = stop_rules_of(rules)
    if health.sent_total >= rules["min_sample"]:
        if health.bounced / health.sent_total >= rules["max_bounce_rate"]:
            return Verdict("suspend", "bounce_rate", f"{health.bounced}/{health.sent_total}")
        if health.opted_out / health.sent_total >= rules["max_opt_out_rate"]:
            return Verdict("suspend", "opt_out_rate", f"{health.opted_out}/{health.sent_total}")
    if health.sent_total >= total_cap:
        return Verdict("end", "cap_total")
    return GO


def send_refusal(
    *,
    status: str,
    expires_at: datetime,
    now: datetime,
    window_start_hour: int,
    window_end_hour: int,
    local_hour: int,
    min_delay_seconds: int,
    seconds_since_last: Optional[float],
) -> Optional[tuple[str, Optional[datetime]]]:
    """At the moment a message of a mandate would leave: (code, retry time) or None. A mandate that is not active or has
    expired sends nothing; the mandate's own window and cadence are stricter than the organisation's, never looser."""
    if now >= expires_at:
        return "expired", None
    if status != "active":
        return "mandate_inactive", None
    if not window_start_hour <= local_hour < window_end_hour:
        return "outside_window", None
    if seconds_since_last is not None and seconds_since_last < min_delay_seconds:
        return "limit_delay", now + timedelta(seconds=min_delay_seconds - seconds_since_last)
    return None
