"""What decides whether and how an e-mail would leave, as THIS process sees it (booleans, names, counts: no value).

The API and the Celery worker read their configuration from their own environment. When a variable is set on one and
not on the other, the API says "ready" while the worker refuses (or the reverse: the screen says dry-run, the worker
sends for real). Each process can describe itself with `fingerprint()`; the worker publishes its own (see
`tasks/health_tasks.py`) and the API compares it with `drift()`.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from services import feature_flags, mail_provider, smtp_svc
from services.outreach_os.drafts import SenderIdentity

# What a person reads as "the e-mail configuration"; every key must be a boolean, a number or a short name.
KEYS = ("live", "sandbox", "kill_switch", "provider", "smtp_host", "sender_configured", "allowlist_size", "test_sink")

LABELS = {
    "live": "envoi réel (FEATURE_LIVE_SENDING)",
    "sandbox": "bac à sable (OUTREACH_SANDBOX)",
    "kill_switch": "arrêt d'urgence (SEND_KILL_SWITCH)",
    "provider": "fournisseur e-mail effectivement utilisé",
    "smtp_host": "serveur SMTP (SMTP_HOST)",
    "sender_configured": "identité de l'expéditeur (OUTREACH_SENDER_*)",
    "allowlist_size": "taille de la liste blanche",
    "test_sink": "enregistreur de test (OUTREACH_TEST_SINK)",
}


def fingerprint() -> dict[str, Any]:
    config = smtp_svc.SmtpConfig.from_env()
    return {
        "live": not feature_flags.dry_run(),
        "sandbox": feature_flags.sandbox(),
        "kill_switch": feature_flags.kill_switch(),
        "provider": mail_provider.email_provider(),
        "smtp_host": config.host if config else None,
        "sender_configured": SenderIdentity.from_env() is not None,
        "allowlist_size": len(feature_flags.live_allowlist()),
        "test_sink": feature_flags.test_sink(),
    }


def drift(api: Mapping[str, Any], worker: Mapping[str, Any]) -> list[str]:
    """The keys on which the two processes disagree (a key the worker did not report counts as a difference)."""
    return [key for key in KEYS if key not in worker or api.get(key) != worker.get(key)]


def drift_text(keys: Sequence[str]) -> str:
    if not keys:
        return ""
    names = ", ".join(LABELS.get(key, key) for key in keys)
    return (
        f"Le worker et l'API n'ont pas la même configuration d'envoi ({names}). Ce que l'écran annonce n'est pas "
        "forcément ce que le worker fera : alignez les variables d'environnement des deux services."
    )
