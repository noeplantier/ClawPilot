"""E-mail draft rendering and compliance checks. Pure: no clock, no I/O.

A draft only states facts that a detected signal backs with evidence — nothing is invented about the
prospect. With no usable fact it falls back to a neutral introduction instead of guessing.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date

from services.outreach_os import email_footer
from services.outreach_os import signals as sig
from services.outreach_os.types import SignalResult, SignalState

TEMPLATE_VERSION = "restaurant-fr-v1"
UNSUBSCRIBE_PLACEHOLDER = "{{unsubscribe_url}}"
_UNSUBSCRIBE_LINK = re.compile(r"https?://\S+/api/unsubscribe/\S+")


def _clean(value: str | None) -> str:
    """An environment value as printed: spaces, newlines and a pair of quotes left by a copy-paste are dropped."""
    text = (value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


@dataclass(frozen=True)
class SenderIdentity:
    """Who the message comes from. Required by law on commercial e-mail; never defaulted to a made-up value."""

    name: str
    company: str
    postal_address: str
    reply_to: str
    whatsapp: str = ""  # optional: printed in the footer only when configured

    @classmethod
    def from_env(cls) -> SenderIdentity | None:
        values = {
            "name": _clean(os.environ.get("OUTREACH_SENDER_NAME")),
            "company": _clean(os.environ.get("OUTREACH_SENDER_COMPANY")),
            "postal_address": _clean(os.environ.get("OUTREACH_SENDER_ADDRESS")),
            "reply_to": _clean(os.environ.get("OUTREACH_SENDER_EMAIL")),
        }
        return (
            cls(**values, whatsapp=_clean(os.environ.get("OUTREACH_SENDER_WHATSAPP"))) if all(values.values()) else None
        )


@dataclass(frozen=True)
class DraftContent:
    subject: str
    body: str
    facts: list[str]  # the evidence-backed statements used, for the reviewer
    template_version: str = TEMPLATE_VERSION


def _fact_lines(results: list[SignalResult], source_name: str, last_updated: date | None) -> list[tuple[str, str]]:
    """(signal key, sentence) for each DETECTED signal that can be stated as an observation."""
    by_key = {r.key: r for r in results if r.state is SignalState.DETECTED}
    lines: list[tuple[str, str]] = []
    if sig.NO_WEBSITE in by_key:
        lines.append(
            (sig.NO_WEBSITE, "Votre établissement ne semble pas disposer d'un site web propre dans l'annuaire.")
        )
    if sig.WEBSITE_UNREACHABLE in by_key:
        lines.append(
            (sig.WEBSITE_UNREACHABLE, "Votre site ne répondait pas correctement lors de notre dernière vérification.")
        )
    if sig.BOOKING_PAGE_MISSING in by_key:
        lines.append(
            (
                sig.BOOKING_PAGE_MISSING,
                "Sur la page d'accueil de votre site, je n'ai pas trouvé de moyen de réserver en ligne.",
            )
        )
    if sig.NOT_MOBILE_FRIENDLY in by_key:
        lines.append(
            (
                sig.NOT_MOBILE_FRIENDLY,
                "La page d'accueil ne semble pas adaptée à l'affichage sur mobile "
                "(vérification automatique, qui peut se tromper).",
            )
        )
    if sig.STALE_LISTING in by_key and last_updated:
        lines.append(
            (sig.STALE_LISTING, f"Votre fiche n'a pas été mise à jour depuis le {last_updated.strftime('%d/%m/%Y')}.")
        )
    return lines


def render_email_draft(
    *,
    business_name: str,
    city: str | None,
    results: list[SignalResult],
    source_name: str,
    last_updated: date | None,
    sender: SenderIdentity,
    unsubscribe_url: str,
) -> DraftContent:
    facts = _fact_lines(results, source_name, last_updated)
    where = f" ({city})" if city else ""
    lines = [
        "Bonjour,",
        "",
        f"Je me permets de vous écrire au sujet de {business_name}{where}.",
    ]
    if facts:
        lines += ["", "Quelques observations, faites à partir d'informations publiques :"]
        lines += [f"- {sentence}" for _, sentence in facts]
    lines += [
        "",
        f"{sender.company} accompagne les restaurateurs sur leur présence en ligne. "
        "Seriez-vous disposé(e) à un court échange pour voir si cela peut vous être utile ?",
        "",
        f"Cordialement,\n{sender.name}",
    ]
    footer = email_footer.render_footer(
        name=sender.name,
        company=sender.company,
        postal_address=sender.postal_address,
        source=f"annuaire « {source_name} »",
        unsubscribe_url=unsubscribe_url,
        reply_to=sender.reply_to,
        whatsapp=sender.whatsapp,
    )
    body = "\n".join(lines) + "\n\n" + footer
    return DraftContent(
        subject=f"À propos de {business_name}",
        body=body,
        facts=[sentence for _, sentence in facts],
    )


def compliance_problems(draft_body: str, sender: SenderIdentity) -> list[str]:
    """Reasons a draft must not be approved. An empty list means the mandatory elements are present."""
    problems: list[str] = []
    for label, value in (
        ("sender name", sender.name),
        ("sender company", sender.company),
        ("postal address", sender.postal_address),
    ):
        if value not in draft_body:
            problems.append(f"missing {label}")
    if "Origine de vos données" not in draft_body and "figurent dans l'annuaire" not in draft_body:  # older drafts
        problems.append("missing data-origin statement")
    if UNSUBSCRIBE_PLACEHOLDER in draft_body or not _UNSUBSCRIBE_LINK.search(draft_body):
        problems.append("missing working unsubscribe link")
    return problems
