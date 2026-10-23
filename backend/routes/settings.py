"""Settings — integration status, computed from the real configuration of this server (nothing hard-coded).

`GET /settings/integrations` returns one entry per integration (`items`) plus the older per-provider blocks.
`POST /settings/integrations/{id}/test` runs the read-only live check of one integration (owner/admin, rate limited).
Only variable NAMES are ever returned, never a value.
"""

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from db.url import describe_database
from deps import get_current_user, require_roles
from models import AIStatus, IntegrationSettings, IntegrationTestOut, OutreachStatus, WebhookStatus
from services import (
    ai_svc,
    feature_flags,
    imap_svc,
    integration_checks,
    integrations_status,
    overpass_svc,
    sendgrid_svc,
    smtp_svc,
    twilio_svc,
)
from services.outreach_os.drafts import SenderIdentity
from services.rate_limit import AttemptLimiter

router = APIRouter(prefix="/settings", tags=["settings"])
decider = require_roles("owner", "admin")
_test_limiter = AttemptLimiter(10, 60.0)


def _env_set() -> frozenset[str]:
    return frozenset(n for n in integrations_status.TRACKED_ENV if os.environ.get(n, "").strip())


async def _ping(session: AsyncSession) -> tuple[bool, int | None]:
    started = time.monotonic()
    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 (an unreachable database is the fact to report)
        await session.rollback()
        return False, None
    return True, int((time.monotonic() - started) * 1000)


@router.get("/integrations", response_model=IntegrationSettings)
async def integrations(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    sender = SenderIdentity.from_env()
    smtp = smtp_svc.status()
    imap = imap_svc.status()
    ai = ai_svc.status()
    db = describe_database()
    db_ok, db_latency = await _ping(session)
    production = os.environ.get("APP_ENV", "").lower() == "production"
    catalog = integrations_status.build(
        integrations_status.Facts(
            env_set=_env_set(),
            app_env=os.environ.get("APP_ENV", ""),
            public_base_url=os.environ.get("PUBLIC_BASE_URL") or None,
            database_kind=db["kind"],
            database_port=db["port"],
            database_ok=db_ok,
            database_latency_ms=db_latency,
            overpass_hosts=tuple(e.split("//", 1)[1].split("/", 1)[0] for e in overpass_svc.endpoints()),
            overpass_cooling=tuple(overpass_svc.cooling_hosts()),
            live_sending=feature_flags.is_enabled("live_sending"),
            external_sources=feature_flags.is_enabled("external_sources"),
            kill_switch=feature_flags.kill_switch(),
            sandbox=feature_flags.sandbox(),
            allowlist_size=len(feature_flags.live_allowlist()),
            sender_configured=sender is not None,
            sender_email=sender.reply_to if sender else None,
            smtp_configured=smtp["configured"],
            smtp_host=smtp["host"],
            smtp_security=smtp["security"],
            imap_configured=imap["configured"],
            imap_host=imap["host"],
            sendgrid_configured=sendgrid_svc.is_configured(),
            sendgrid_from=os.environ.get("SENDGRID_FROM_EMAIL") or None,
            twilio_configured=twilio_svc.is_configured(),
            twilio_from=os.environ.get("TWILIO_WHATSAPP_FROM") or None,
            twilio_sid_is_account=(twilio_svc.SID or "").startswith("AC"),
            twilio_signature_ready=bool(twilio_svc.TOKEN),
            sendgrid_signature_ready=bool(sendgrid_svc.WEBHOOK_PUBLIC_KEY),
            ai=ai,
        )
    )
    return IntegrationSettings(
        sendgrid_from_email=os.environ.get("SENDGRID_FROM_EMAIL") or None,
        twilio_whatsapp_from=os.environ.get("TWILIO_WHATSAPP_FROM") or None,
        twilio_account_sid_configured=twilio_svc.is_configured(),
        sendgrid_configured=sendgrid_svc.is_configured(),
        ai=AIStatus(**ai),
        outreach=OutreachStatus(
            dry_run=feature_flags.dry_run(),
            live_sending_flag=feature_flags.is_enabled("live_sending"),
            kill_switch=feature_flags.kill_switch(),
            sender_configured=sender is not None,
            sender_email=sender.reply_to if sender else None,
            smtp_configured=smtp["configured"],
            smtp_host=smtp["host"],
            imap_configured=imap["configured"],
            imap_host=imap["host"],
            sandbox=feature_flags.sandbox(),
            allowlist_size=len(feature_flags.live_allowlist()),
        ),
        webhooks=WebhookStatus(
            production=production,
            twilio_signature_ready=bool(twilio_svc.TOKEN),
            twilio_webhook_url_set=bool(os.environ.get("TWILIO_WEBHOOK_URL")),
            sendgrid_signature_ready=bool(sendgrid_svc.WEBHOOK_PUBLIC_KEY),
        ),
        items=catalog["items"],
        counts=catalog["counts"],
        generated_at=datetime.now(timezone.utc),
    )


def _checks() -> dict:
    """The server-side checks by integration id. A function, so tests can swap it for offline replays."""
    return {
        "osm": integration_checks.osm,
        "registry": integration_checks.registry,
        "smtp": integration_checks.smtp,
        "imap": integration_checks.imap,
        "sendgrid": integration_checks.sendgrid,
        "twilio": integration_checks.twilio,
    }


@router.post("/integrations/{item_id}/test", response_model=IntegrationTestOut)
async def test_integration(
    item_id: str, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    if item_id in integrations_status.BROWSER_TESTS:
        raise HTTPException(status_code=400, detail="This service is called from your browser: it is tested there")
    if item_id not in integrations_status.TESTABLE:
        raise HTTPException(status_code=404, detail="No live test for this integration")
    key = str(uuid.UUID(user["org_id"]))
    wait = _test_limiter.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429, detail="Test limit reached: wait a minute", headers={"Retry-After": str(wait)}
        )
    _test_limiter.record(key)
    if item_id == "database":
        ok, latency = await _ping(session)
        result = integration_checks.database(latency, None if ok else "The database did not answer a query.")
    else:
        result = await asyncio.to_thread(_checks()[item_id])  # blocking sockets: never on the event loop
    return IntegrationTestOut(id=item_id, checked_at=datetime.now(timezone.utc), **result)
