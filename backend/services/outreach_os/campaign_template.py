"""The controlled message template of a campaign, its per-establishment rendering and what an approval is bound to.

Pure: no I/O, no AI. One approved template is the common frame; each message is rendered for its establishment from a
fixed set of placeholders, so nothing is rewritten after the approval and nothing needs hundreds of paid variants.

* The values come from the prospect's own record and from signals that were DETECTED (and not dismissed). A value that
  came from a public source is data: it is sanitised and inserted, never interpreted, and never reaches an AI.
* The sentence about the website follows the three states: present (only verifiable findings), none identified after a
  search (a prudent wording), unknown (no claim at all: an empty field proves nothing).
* An approval is tied to a hash of the template, of the zone, of the offer and of the sender. Changing any of them
  makes the approval stale; the person approves again, knowingly.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from services.outreach_os import campaign_plan

PLACEHOLDERS = ("nom", "activite", "ville", "constat", "offre", "pitch", "cta", "expediteur")
REQUIRED = ("nom",)  # a message that does not name the establishment is a mass mailing: refused
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_]+)\s*\}\}")
_SINGLE_BRACE = re.compile(r"(?<!\{)\{[A-Za-z_][^{}]*\}(?!\})")
MAX_FACTS = 2
VALUE_LIMIT = 120

# What the word "constat" renders as, by language (the one place a sentence about the website is written).
CAUTIOUS_NO_SITE = {
    "fr": "Sauf erreur de ma part, je n'ai pas identifié de site officiel pour {nom}.",
    "en": "Unless I am mistaken, I could not identify an official website for {nom}.",
}
FACTS_INTRO = {
    "fr": "Quelques observations, faites à partir d'informations publiques :",
    "en": "A few observations, made from public information:",
}
NO_WEBSITE_FACT_KEY = "no_website"

SITE_FOUND = "site_found"
SITE_UNREACHABLE = "site_unreachable"
SITE_NONE_IDENTIFIED = "none_identified"
SITE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class Problem:
    code: str
    label: str


# ---------------------------------------------------------------------------------------------- default template
def default_template(offer: Mapping[str, str], *, language: Optional[str] = None) -> tuple[str, str]:
    """(subject, body) pre-filled from the configured offer: editable, never obligatory to rewrite."""
    lang = language or offer.get("language", "fr")
    if lang == "en":
        subject = "About {{nom}}"
        body = (
            "Hello,\n\nI am writing about {{nom}} ({{ville}}).\n\n{{constat}}\n\n{{pitch}}\n\n{{cta}}\n\n"
            "Kind regards,\n{{expediteur}}"
        )
    else:
        subject = "À propos de {{nom}}"
        body = (
            "Bonjour,\n\nJe me permets de vous écrire au sujet de {{nom}} ({{ville}}).\n\n{{constat}}\n\n{{pitch}}\n\n"
            "{{cta}}\n\nCordialement,\n{{expediteur}}"
        )
    return subject, body


# ---------------------------------------------------------------------------------------------- validation
def used_placeholders(*texts: str) -> list[str]:
    found: list[str] = []
    for text in texts:
        for match in _PLACEHOLDER.finditer(text or ""):
            name = match.group(1).lower()
            if name not in found:
                found.append(name)
    return found


def problems(subject: str, body: str) -> list[Problem]:
    """What makes a template unusable. Nothing is repaired silently."""
    out: list[Problem] = []
    if not (subject or "").strip():
        out.append(Problem("empty_subject", "Objet vide"))
    if not (body or "").strip():
        out.append(Problem("empty_body", "Corps vide"))
    names = used_placeholders(subject, body)
    unknown = [n for n in names if n not in PLACEHOLDERS]
    if unknown:
        out.append(Problem("unknown_placeholder", "Champ inconnu : " + ", ".join("{{" + n + "}}" for n in unknown)))
    missing = [n for n in REQUIRED if n not in names]
    if missing:
        out.append(Problem("missing_required", "Le message doit nommer l'établissement : {{nom}} est absent"))
    stray = _SINGLE_BRACE.findall(subject or "") + _SINGLE_BRACE.findall(body or "")
    if stray:
        out.append(Problem("single_brace", "Accolades simples non remplacées : " + ", ".join(stray[:3])))
    return out


# ---------------------------------------------------------------------------------------------- rendering
def sanitize_value(value: Optional[str], limit: int = VALUE_LIMIT) -> str:
    """A value from a public source is data: one line, no template syntax, no control characters, bounded."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", value or "")
    text = text.replace("{{", "").replace("}}", "").replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip()[:limit]


@dataclass(frozen=True)
class RenderContext:
    nom: str
    activite: Optional[str]
    ville: Optional[str]
    site_state: str
    facts: Sequence[tuple[str, str]]  # (signal key, sentence) of the signals detected now, from `observed_facts`
    offre: str
    pitch: str
    cta: str
    expediteur: str
    language: str = "fr"


@dataclass
class Rendered:
    subject: str
    body: str
    facts: list[str] = field(
        default_factory=list
    )  # the observed sentences this message rests on (the reviewer's evidence)
    site_state: str = SITE_UNKNOWN
    problems: list[campaign_plan.Problem] = field(default_factory=list)


def constat_block(ctx: RenderContext) -> tuple[str, list[str]]:
    """(the text `constat` stands for, the observed sentences it rests on). Empty when nothing is established."""
    lang = ctx.language if ctx.language in FACTS_INTRO else "fr"
    lines: list[str] = []
    used: list[str] = []
    if ctx.site_state == SITE_NONE_IDENTIFIED:
        # an established "no site found" is said prudently; the observed sentence stays as evidence
        lines.append(CAUTIOUS_NO_SITE[lang].format(nom=sanitize_value(ctx.nom)))
        used += [sentence for key, sentence in ctx.facts if key == NO_WEBSITE_FACT_KEY]
        others = [(k, s) for k, s in ctx.facts if k != NO_WEBSITE_FACT_KEY][:MAX_FACTS]
    else:
        others = [(k, s) for k, s in ctx.facts if k != NO_WEBSITE_FACT_KEY][:MAX_FACTS]
    if others:
        lines += ([FACTS_INTRO[lang]] if not lines else []) + [f"- {sentence}" for _, sentence in others]
        used += [sentence for _, sentence in others]
    return "\n".join(lines), used


def _fill(text: str, values: Mapping[str, str]) -> str:
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1).lower(), m.group(0)), text)


def render(subject: str, body: str, ctx: RenderContext) -> Rendered:
    """Fill the placeholders for one establishment. A placeholder that has no value is reported, never invented."""
    constat, used = constat_block(ctx)
    values = {
        "nom": sanitize_value(ctx.nom),
        "activite": sanitize_value(ctx.activite),
        "ville": sanitize_value(ctx.ville),
        "offre": sanitize_value(ctx.offre),
        "pitch": sanitize_value(ctx.pitch, 600),
        "cta": sanitize_value(ctx.cta, 160),
        "expediteur": sanitize_value(ctx.expediteur),
        "constat": constat,  # already assembled from sanitised parts
    }
    wanted = used_placeholders(subject, body)
    gaps = [name for name in ("nom", "activite", "ville") if name in wanted and not values[name]]
    out_body = _fill(body, values)
    if not constat:  # no established observation: the paragraph disappears whole, not a blank hole
        out_body = re.sub(r"\n{3,}", "\n\n", out_body)
    out_subject = _fill(subject, values)
    found = campaign_plan.unresolved_variables(out_subject, out_body)
    issues: list[campaign_plan.Problem] = []
    if gaps:
        issues.append(
            campaign_plan.Problem(
                "missing_value", "Donnée absente pour ce prospect : " + ", ".join("{{" + g + "}}" for g in gaps)
            )
        )
    if found:
        issues.append(campaign_plan.Problem("unresolved_variable", "Variable non résolue : " + ", ".join(found)))
    return Rendered(out_subject.strip(), out_body.strip(), used, ctx.site_state, issues)


# ---------------------------------------------------------------------------------------------- hashes and approval
def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def content_hash(subject: str, body: str) -> str:
    """Whitespace-only edits keep the hash: re-wrapping a line is not a new message."""
    return _digest({"subject": normalize_text(subject), "body": normalize_text(body)})


def offer_hash(offer: Optional[Mapping[str, str]]) -> Optional[str]:
    if not offer:
        return None
    return _digest({k: normalize_text(str(offer.get(k, ""))) for k in ("name", "pitch", "cta", "language")})


def zone_hash(zone: Optional[Mapping[str, Any]]) -> Optional[str]:
    """The perimeter that was approved: the box and the category, not the label or the time it was drawn."""
    if not zone:
        return None
    try:
        box = {k: round(float(zone[k]), 5) for k in ("south", "west", "north", "east")}
    except (KeyError, TypeError, ValueError):
        return None
    return _digest({**box, "category": normalize_text(str(zone.get("category", "")))})


def sender_fingerprint(name: str, company: str, address: str, email: str) -> str:
    return _digest([normalize_text(v).lower() for v in (name, company, address, email)])


@dataclass(frozen=True)
class Binding:
    """What an approval was given for."""

    content_hash: str
    zone_hash: Optional[str]
    offer_hash: Optional[str]
    sender_fp: Optional[str]
    expires_at: Optional[datetime]
    revoked: bool = False


@dataclass(frozen=True)
class Current:
    content_hash: str
    zone_hash: Optional[str]
    offer_hash: Optional[str]
    sender_fp: Optional[str]


REASONS = {
    "revoked": "Approbation révoquée",
    "expired": "Approbation expirée",
    "template_changed": "Le modèle a changé depuis l'approbation",
    "zone_changed": "La zone a changé depuis l'approbation",
    "offer_changed": "L'offre a changé depuis l'approbation",
    "sender_changed": "L'expéditeur a changé depuis l'approbation",
}


def approval_reasons(binding: Optional[Binding], current: Current, now: datetime) -> list[str]:
    """Why an approval no longer covers the campaign as it is now; empty = it does. No binding = never approved."""
    if binding is None:
        return ["not_approved"]
    out: list[str] = []
    if binding.revoked:
        out.append("revoked")
    if binding.expires_at is not None and now >= binding.expires_at:
        out.append("expired")
    if binding.content_hash != current.content_hash:
        out.append("template_changed")
    if binding.zone_hash != current.zone_hash:
        out.append("zone_changed")
    if binding.offer_hash != current.offer_hash:
        out.append("offer_changed")
    if binding.sender_fp != current.sender_fp:
        out.append("sender_changed")
    return out


def reason_label(code: str) -> str:
    return REASONS.get(code) or ("Campagne non approuvée" if code == "not_approved" else code)
