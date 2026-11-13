"""Which provider sends the e-mail, and how to move to a dedicated B2B relay.

Read-only and secret-free: the host of the provider in use, the public settings of the known relays, and the NAMES
of the server variables to set. Moving to a relay is done on the server (SMTP_*), never from this screen: a password
does not travel through the application. Replies keep being read from the mailbox of IMAP_*, whatever relay sends.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from deps import get_current_user
from services import campaign_launch, feature_flags, imap_svc, smtp_svc
from services.outreach_os import provider_policy

router = APIRouter(prefix="/email-providers", tags=["outbound"])

SERVER_VARIABLES = ["SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USERNAME", "SMTP_PASSWORD"]


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
        },
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
        "server_variables": SERVER_VARIABLES,  # names only, never a value
    }
