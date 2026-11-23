"""Which provider sends the e-mail, and how to change it.

Read-only and secret-free: the provider in use, the API channels (Resend, then Brevo: tried before SMTP, see
mail_provider.live_adapter), the public settings of the known SMTP relays, and the NAMES of the server variables. A
change is made on the server, never from this screen: a key or a password does not travel through the application.
Replies keep being read from the mailbox of IMAP_*, whatever sends.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from deps import get_current_user
from services import brevo_svc, campaign_launch, feature_flags, imap_svc, resend_svc, smtp_svc
from services.outreach_os import provider_policy

router = APIRouter(prefix="/email-providers", tags=["outbound"])

SMTP_VARIABLES = ["SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USERNAME", "SMTP_PASSWORD"]
SERVER_VARIABLES = ["RESEND_API_KEY", "BREVO_API_KEY", *SMTP_VARIABLES]
API_IDS = {"resend": "resend_api", "brevo": "brevo_api"}  # the ProviderInfo id when that channel carries the e-mail


def _api_channels(current_id: str) -> list[dict]:
    """The HTTPS channels, in the order the server tries them. Resend is recommended: port 443 works where outbound
    SMTP ports are closed (a free Render instance). "Configured" is a key being set, never a test passed."""
    rows = [
        (
            "resend",
            "Resend",
            "RESEND_API_KEY",
            resend_svc.is_configured(),
            "API HTTPS, essayé en premier ; domaine à vérifier dans Resend.",
        ),
        (
            "brevo",
            "Brevo",
            "BREVO_API_KEY",
            brevo_svc.is_configured(),
            "API HTTPS, essayé après Resend ; expéditeur à vérifier dans Brevo.",
        ),
    ]
    return [
        {
            "id": cid,
            "name": name,
            "variable": variable,
            "configured": configured,
            "active": current_id == API_IDS[cid],
            "recommended": cid == "resend",
            "note": note,
        }
        for cid, name, variable, configured, note in rows
    ]


@router.get("")
async def providers(user: dict = Depends(get_current_user)):
    current = campaign_launch.provider_info()
    relay = provider_policy.relay_of(current.host)
    return {
        "current": {
            "id": current.id,
            "label": current.label,
            "host": current.host,
            "cold_outreach": current.cold_outreach,
            "restriction": current.restriction,
            "is_relay": relay is not None,
            "shared_mailbox": current.cold_outreach == provider_policy.OPT_IN_REQUIRED,
            "is_api": current.id in API_IDS.values(),
        },
        "order": ["resend", "brevo", "smtp"],  # mail_provider.live_adapter: the first configured one carries the e-mail
        "api_channels": _api_channels(current.id),
        "smtp_configured": smtp_svc.is_configured(),
        "replies_read": imap_svc.is_configured(),
        "live_sending": feature_flags.is_enabled("live_sending"),
        "relays": [
            {
                "id": p.id,
                "name": p.name,
                "host": p.host,
                "port": p.port,
                "security": p.security,
                "username_hint": p.username_hint,
                "note": p.note,
                "recommended": p.recommended,
                "active": relay is not None and relay.id == p.id,
            }
            for p in provider_policy.B2B_RELAYS
        ],
        "smtp_variables": SMTP_VARIABLES,  # names only, never a value
        "server_variables": SERVER_VARIABLES,
    }
