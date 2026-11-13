"""Which provider would carry a campaign, what it forbids, and who may receive a campaign through it. Pure: no I/O.

An available quota is not an authorization. A shared mailbox provider (Hostinger, and its Titan webmail) sells an
inbox, not a bulk sending service: its terms forbid unsolicited bulk e-mail, so a contact found in a public directory,
with no opt-in, is not presented as authorized to receive a *campaign* through it. A provider the application does not
know is reported as "unverified": the operator reads its terms, nothing is blocked on a guess.

The provider is the one that would carry a real message (SMTP, else SendGrid), whether or not live sending is switched
on: a rehearsal in dry-run excludes the same recipients the real run would.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

OPT_IN_REQUIRED = "opt_in_required"
UNVERIFIED = "unverified"
NOT_CONFIGURED = "not_configured"

# What a recipient's authorization rests on, from the strongest to "nothing recorded".
BASIS_OPT_IN = "opt_in"  # an explicit consent recorded for e-mail
BASIS_DECLARED_CONSENT = "declared_consent"  # a supplied list whose legal basis was declared "consent" at import
BASIS_LEGITIMATE_INTEREST = "legitimate_interest_b2b"  # a supplied list declared as B2B legitimate interest
BASIS_PUBLIC_DIRECTORY = "public_directory"  # found in a public directory: no relationship, no consent recorded

_LEGAL_BASIS = re.compile(r"legal basis:\s*([a-z0-9_]+)", re.IGNORECASE)


@dataclass(frozen=True)
class ProviderInfo:
    id: str  # "smtp_hostinger" | "smtp" | "sendgrid" | "none"
    label: str
    host: Optional[str]
    cold_outreach: str  # OPT_IN_REQUIRED | UNVERIFIED | NOT_CONFIGURED
    restriction: str  # one sentence for the operator, in French (it is shown as is)


@dataclass(frozen=True)
class Authorization:
    ok: bool
    basis: str
    code: Optional[str]  # None when ok; "provider_requires_opt_in" otherwise
    label: str


@dataclass(frozen=True)
class RelayPreset:
    """A dedicated sending relay (a service made to send e-mail, unlike a shared mailbox): public SMTP settings only.
    The login and the password are never here: they are the operator's, set on the server (SMTP_USERNAME and
    SMTP_PASSWORD)."""

    id: str
    name: str
    host: str
    port: int
    security: str  # "starttls" | "ssl"
    username_hint: str  # what goes in SMTP_USERNAME, in words
    note: str  # one sentence for the operator, in French
    domains: tuple[str, ...] = ()  # the provider's SMTP domains: any host under one of them is this relay
    recommended: bool = False


B2B_RELAYS: tuple[RelayPreset, ...] = (
    RelayPreset(
        "brevo",
        "Brevo",
        "smtp-relay.brevo.com",
        587,
        "starttls",
        "l'identifiant SMTP affiché dans Brevo (SMTP et API)",
        "Société européenne, offre gratuite avec un quota quotidien ; l'expéditeur doit être vérifié dans Brevo.",
        domains=("brevo.com", "sendinblue.com"),
        recommended=True,
    ),
    RelayPreset(
        "mailjet",
        "Mailjet",
        "in-v3.mailjet.com",
        587,
        "starttls",
        "la clé API Mailjet (le mot de passe est la clé secrète)",
        "Société européenne, offre gratuite avec un quota quotidien.",
        domains=("mailjet.com",),
    ),
    RelayPreset(
        "sendgrid",
        "SendGrid (SMTP)",
        "smtp.sendgrid.net",
        587,
        "starttls",
        "le mot « apikey » (le mot de passe est la clé API)",
        "Relais américain ; le domaine d'envoi doit être authentifié.",
        domains=("sendgrid.net",),
    ),
    RelayPreset(
        "mailgun",
        "Mailgun",
        "smtp.eu.mailgun.org",
        587,
        "starttls",
        "l'identifiant SMTP du domaine dans Mailgun",
        "Région UE ; le domaine d'envoi doit être vérifié.",
        domains=("mailgun.org",),
    ),
    RelayPreset(
        "google",
        "Google Workspace",
        "smtp.gmail.com",
        587,
        "starttls",
        "l'adresse de la boîte (le mot de passe est un mot de passe d'application)",
        "Une boîte Workspace sur un domaine dédié à la prospection, à faible volume.",
        domains=("gmail.com", "googlemail.com"),
    ),
    RelayPreset(
        "microsoft",
        "Microsoft 365",
        "smtp.office365.com",
        587,
        "starttls",
        "l'adresse de la boîte",
        "Une boîte Microsoft 365 sur un domaine dédié à la prospection, à faible volume.",
        domains=("office365.com", "outlook.com"),
    ),
    RelayPreset(
        "zoho",
        "Zoho Mail",
        "smtp.zoho.eu",
        587,
        "starttls",
        "l'adresse de la boîte",
        "Hébergement européen ; à faible volume.",
        domains=("zoho.eu", "zoho.com"),
    ),
)


def relay_of(host: Optional[str]) -> Optional[RelayPreset]:
    """The known relay this SMTP host belongs to (exact host, or a regional variant of it), else None."""
    h = (host or "").strip().lower()
    if not h:
        return None
    for preset in B2B_RELAYS:
        if h == preset.host or any(h == d or h.endswith("." + d) for d in preset.domains):
            return preset
    return None


def _is_hostinger(host: str) -> bool:
    host = host.lower()
    return "hostinger" in host or host == "titan.email" or host.endswith(".titan.email")


def identify(*, smtp_host: Optional[str], sendgrid_configured: bool) -> ProviderInfo:
    host = (smtp_host or "").strip().lower() or None
    if host and _is_hostinger(host):
        return ProviderInfo(
            id="smtp_hostinger",
            label=f"SMTP Hostinger ({host})",
            host=host,
            cold_outreach=OPT_IN_REQUIRED,
            restriction=(
                "Messagerie mutualisée Hostinger : ses conditions d'utilisation interdisent l'envoi en masse non "
                "sollicité. Seuls les destinataires avec un opt-in explicite (ou une base « consentement » déclarée à "
                "l'import) sont "
                "autorisés à recevoir une campagne par ce fournisseur ; un quota d'envoi disponible ne vaut pas "
                "autorisation. Relisez les conditions du fournisseur avant tout envoi réel."
            ),
        )
    relay = relay_of(host)
    if host and relay is not None:
        return ProviderInfo(
            id=f"smtp_{relay.id}",
            label=f"{relay.name} ({host})",
            host=host,
            cold_outreach=UNVERIFIED,
            restriction=(
                f"{relay.name} : relais d'envoi dédié, pas une messagerie mutualisée. L'application ne lit pas ses "
                "conditions : vérifiez qu'elles autorisent la prospection B2B pour votre usage (base légale, "
                "désinscription, volume) avant tout envoi réel ; un quota disponible ne vaut pas autorisation."
            ),
        )
    if host:
        return ProviderInfo(
            id="smtp",
            label=f"SMTP ({host})",
            host=host,
            cold_outreach=UNVERIFIED,
            restriction=(
                f"Fournisseur SMTP « {host} » : l'application ne connaît pas ses conditions. Vérifiez qu'elles "
                "autorisent "
                "la prospection B2B avant tout envoi réel ; un quota disponible ne vaut pas autorisation."
            ),
        )
    if sendgrid_configured:
        return ProviderInfo(
            id="sendgrid",
            label="SendGrid",
            host=None,
            cold_outreach=UNVERIFIED,
            restriction=(
                "SendGrid : l'application ne vérifie pas vos conditions d'usage. Vérifiez qu'elles autorisent la "
                "prospection B2B avant tout envoi réel ; un quota disponible ne vaut pas autorisation."
            ),
        )
    return ProviderInfo(
        id="none",
        label="Aucun fournisseur configuré",
        host=None,
        cold_outreach=NOT_CONFIGURED,
        restriction=(
            "Aucun fournisseur e-mail n'est configuré (SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, ou SENDGRID_API_KEY) : "
            "rien ne peut partir pour de vrai, seule la simulation (dry-run) est possible."
        ),
    )


def legal_basis_of(license_notes: list[Optional[str]]) -> Optional[str]:
    """The legal basis a supplied list was declared with (the importer writes it into the source's licence note), else
    None."""
    for note in reversed(license_notes):
        match = _LEGAL_BASIS.search(note or "")
        if match:
            return match.group(1).lower()
    return None


def basis_of(*, consent_status: str, legal_basis: Optional[str]) -> str:
    if consent_status == "opted_in":
        return BASIS_OPT_IN
    if legal_basis == "consent":
        return BASIS_DECLARED_CONSENT
    if legal_basis == "legitimate_interest_b2b":
        return BASIS_LEGITIMATE_INTEREST
    return BASIS_PUBLIC_DIRECTORY


BASIS_LABELS = {
    BASIS_OPT_IN: "opt-in explicite enregistré",
    BASIS_DECLARED_CONSENT: "consentement déclaré à l'import",
    BASIS_LEGITIMATE_INTEREST: "intérêt légitime B2B déclaré à l'import (pas d'opt-in)",
    BASIS_PUBLIC_DIRECTORY: "annuaire public, aucun opt-in enregistré",
}


def authorize(info: ProviderInfo, *, consent_status: str, legal_basis: Optional[str]) -> Authorization:
    """May this recipient receive a campaign through this provider? Only an opt-in counts where the provider requires
    one."""
    basis = basis_of(consent_status=consent_status, legal_basis=legal_basis)
    if info.cold_outreach == OPT_IN_REQUIRED and basis not in (BASIS_OPT_IN, BASIS_DECLARED_CONSENT):
        return Authorization(
            False,
            basis,
            "provider_requires_opt_in",
            f"Non autorisé via {info.label} : {BASIS_LABELS[basis]}",
        )
    return Authorization(True, basis, None, f"Autorisé : {BASIS_LABELS[basis]}")
