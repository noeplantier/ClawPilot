"""Outbound dispatch: send an approved draft through a channel adapter, under limits and a kill switch.

Dry-run unless `FEATURE_LIVE_SENDING` is on; then the SMTP adapter is used (refused when it is not fully configured).
Reading is open to any member; dispatching, simulating events, testing the SMTP connection and changing limits
need owner/admin. Refused attempts are written to the audit log (committed before the 4xx is returned).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import OutboundMessage
from db.session import get_db_session
from deps import get_current_user, require_roles
from models import (
    DispatchIn,
    InboxSyncOut,
    LimitsOut,
    LimitsPatch,
    OutboundEventOut,
    OutboundMessageDetail,
    OutboundMessageOut,
    SendStatusOut,
    SimulateIn,
    SmtpCheckIn,
    SmtpCheckOut,
)
from repositories import audit_repo, draft_repo, outbound_repo, outreach_repo, send_policy_repo
from routes._refusal import refusal
from services import feature_flags, imap_svc, inbox_sync, send_gate, smtp_svc
from services.outreach_os import channels
from services.outreach_os import dispatch as dispatch_svc
from services.outreach_os import drafts, sandbox

router = APIRouter(prefix="/outbound", tags=["outbound"])
decider = require_roles("owner", "admin")


def _account(user: dict) -> uuid.UUID:
    return uuid.UUID(user["org_id"])


def _out(m: OutboundMessage, created: bool = True) -> OutboundMessageOut:
    return OutboundMessageOut(
        id=str(m.id),
        lead_id=str(m.lead_id),
        draft_id=str(m.draft_id) if m.draft_id else None,
        channel=m.channel,
        to_email=m.to_email,
        subject=m.subject,
        status=m.status,
        dry_run=m.dry_run,
        adapter=m.adapter,
        provider_message_id=m.provider_message_id,
        error=m.error,
        dispatched_at=m.dispatched_at,
        created=created,
    )


# ---------------------------------------------------------------- status and limits
CHANNEL_QUERY = Query(default="email", pattern="^(email|whatsapp)$")


@router.get("/status", response_model=SendStatusOut)
async def status(
    channel: str = CHANNEL_QUERY,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    s = await send_gate.status(session, _account(user), channel, datetime.now(timezone.utc))
    return SendStatusOut(
        dry_run=s.dry_run,
        kill_switch=s.halted_by_env,
        paused=s.paused,
        limits=LimitsOut(
            max_per_day=s.limits.max_per_day,
            max_per_hour=s.limits.max_per_hour,
            min_delay_seconds=s.limits.min_delay_seconds,
            sending_paused=s.paused,
        ),
        sent_today=s.sent_today,
        sent_last_hour=s.sent_last_hour,
        last_dispatched_at=s.last_dispatched_at,
        next_allowed_at=s.next_allowed_at,
        blocked_by=s.blocked_by,
    )


def _limits_out(policy: send_policy_repo.EffectivePolicy) -> LimitsOut:
    return LimitsOut(
        max_per_day=policy.max_per_day,
        max_per_hour=policy.max_per_hour,
        min_delay_seconds=policy.min_delay_seconds,
        sending_paused=policy.sending_paused,
    )


@router.get("/limits", response_model=LimitsOut)
async def get_limits(
    channel: str = CHANNEL_QUERY,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return _limits_out(await send_policy_repo.get_policy(session, _account(user), channel))


@router.put("/limits", response_model=LimitsOut)
async def put_limits(
    payload: LimitsPatch,
    channel: str = CHANNEL_QUERY,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Change the limits and/or pause sending for this organisation (`sending_paused` is the account kill switch)."""
    changes = payload.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to change")
    await send_policy_repo.update_limits(session, _account(user), channel, **changes)
    await audit_repo.log(
        session,
        _account(user),
        action="send_limits.changed",
        resource_type="send_policy",
        actor_user_id=uuid.UUID(user["id"]),
        diff={**changes, "channel": channel},
    )
    return _limits_out(await send_policy_repo.get_policy(session, _account(user), channel))


# ---------------------------------------------------------------- dispatch
@router.post("/dispatch", response_model=OutboundMessageOut)
async def dispatch(
    payload: DispatchIn,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=200),
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Dispatch of an approved draft (dry-run, or SMTP when live). A draft yields at most one message; same key ⇒ same
    message. A `failed` attempt may be dispatched again; a message left in `sending` (outcome unknown) never is."""
    draft = await draft_repo.get(session, _account(user), payload.draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    try:
        message, created = await dispatch_svc.dispatch_draft(
            session,
            _account(user),
            draft,
            now=datetime.now(timezone.utc),
            user_id=uuid.UUID(user["id"]),
            idempotency_key=idempotency_key,
            live_adapter=smtp_svc.adapter_from_env(),
        )
    except dispatch_svc.DispatchBlocked as blocked:
        raise await refusal(session, user, blocked, resource_id=draft.id)
    return _out(message, created)


# ---------------------------------------------------------------- SMTP connection test
TEST_SUBJECT = "[Plantiers - OutreachOS] SMTP connection test"


def _test_body(sender: drafts.SenderIdentity) -> str:
    return (
        "Ceci est un message de test technique envoyé depuis Plantiers - OutreachOS. Il vérifie la connexion SMTP et "
        "l'authentification de l'expéditeur ; ce n'est pas un message de prospection.\n\n"
        f"Expéditeur : {sender.name}, {sender.company}, {sender.postal_address}\n"
        "Origine des données : aucune donnée de prospect ; l'adresse destinataire a été saisie par un administrateur.\n"
        f"Pour ne plus recevoir de test : écrivez à {sender.reply_to}.\n"
    )


@router.post("/test-send", response_model=SmtpCheckOut)
async def smtp_test_send(
    payload: SmtpCheckIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    """Send ONE technical message to verify the real SMTP connection and the sender address, before any prospect.

    Only to the sender's own address or to `OUTREACH_LIVE_ALLOWLIST` (never a prospect), only when live sending is on,
    through the same kill switch, pause and limits as everything else. Records an `email_sends` row (so it counts toward
    the limits) but no outreach event, so the analytics are not polluted.
    """
    account_id = _account(user)

    async def refuse(code: str, message: str):
        return await refusal(
            session,
            user,
            send_gate.SendBlocked(code, message),
            resource_type="smtp_test",
            action="smtp_test.blocked",
            channel="email",
        )

    sender = drafts.SenderIdentity.from_env()
    if sender is None:
        raise await refuse("sender_not_configured", "Sender identity is not configured (OUTREACH_SENDER_*)")
    if feature_flags.dry_run():
        raise await refuse("live_not_available", "FEATURE_LIVE_SENDING is off: there is no real connection to test")
    own = sender.reply_to.strip().lower()
    to = str(payload.to).strip().lower()
    if not sandbox.is_allowed(to, (own, *feature_flags.live_allowlist())):
        raise await refuse(
            "sandbox_recipient", "A test only goes to the sender's own address or to OUTREACH_LIVE_ALLOWLIST"
        )
    adapter = smtp_svc.adapter_from_env(extra_allowed=(own,))
    if adapter is None:
        raise await refuse(
            "live_not_available", "SMTP settings are incomplete (SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD)"
        )
    try:
        await send_gate.check(session, account_id, "email")
    except send_gate.SendBlocked as blocked:
        raise await refusal(
            session, user, blocked, resource_type="smtp_test", action="smtp_test.blocked", channel="email"
        )

    body = _test_body(sender)
    message = channels.ChannelMessage(
        to=to,
        subject=TEST_SUBJECT,
        body=body,
        sender_name=sender.name,
        sender_email=own,
        idempotency_key=f"smtp-test:{uuid.uuid4()}",
        headers={"List-Unsubscribe": f"<mailto:{own}?subject=unsubscribe>"},
    )
    result = await asyncio.to_thread(adapter.send, message)
    await outreach_repo.create_email_send(
        session,
        account_id,
        to_email=to,
        subject=TEST_SUBJECT,
        body=body,
        status="sent" if result.status == "sent" else "failed",
        provider_message_id=result.provider_id,
        error=result.error,
    )
    await audit_repo.log(
        session,
        account_id,
        action=f"smtp_test.{result.status}",
        resource_type="smtp_test",
        actor_type="user",
        actor_user_id=uuid.UUID(user["id"]),
        diff={"recipient_domain": to.rsplit("@", 1)[1], "adapter": adapter.name},
    )
    return SmtpCheckOut(
        status=result.status, to=to, adapter=adapter.name, provider_message_id=result.provider_id, error=result.error
    )


# ---------------------------------------------------------------- inbound mailbox
@router.post("/sync-inbox", response_model=InboxSyncOut)
async def sync_inbox(user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)):
    """Read the sending mailbox now (the beat task does it every 5 minutes where a worker runs): replies, hard bounces,
    STOP. 501 when IMAP_* is not configured; a connection or login failure is a 502 that names the error class only."""
    mailbox = imap_svc.mailbox_from_env()
    if mailbox is None:
        raise HTTPException(status_code=501, detail="IMAP is not configured (IMAP_HOST, IMAP_USERNAME, IMAP_PASSWORD)")
    try:
        result = await inbox_sync.sync(session, mailbox)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Mailbox unreachable ({type(exc).__name__})")
    return InboxSyncOut(**result.as_dict())


# ---------------------------------------------------------------- history
@router.get("", response_model=list[OutboundMessageOut])
async def list_messages(
    status: Optional[str] = Query(default=None, pattern="^(sending|sent|failed|bounced|replied)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await outbound_repo.list_messages(session, _account(user), status=status, limit=limit, offset=offset)
    return [_out(m) for m in rows]


@router.get("/{message_id}", response_model=OutboundMessageDetail)
async def get_message(
    message_id: str, user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)
):
    message = await outbound_repo.get(session, _account(user), message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    events = await outbound_repo.events_of(session, message.id)
    return OutboundMessageDetail(
        **_out(message).model_dump(),
        body=message.body,
        events=[
            OutboundEventOut(id=str(e.id), event_type=e.event_type, detail=e.detail, created_at=e.created_at)
            for e in events
        ],
    )


@router.post("/{message_id}/simulate", response_model=OutboundMessageOut)
async def simulate(
    message_id: str,
    payload: SimulateIn,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Dry-run stand-in for the provider webhook: a hard bounce (suppresses the address) or a reply
    (a STOP-style reply opts the prospect out immediately)."""
    message = await outbound_repo.get(session, _account(user), message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    try:
        await dispatch_svc.simulate_event(
            session,
            _account(user),
            message,
            event=payload.event,
            text=payload.text,
            user_id=uuid.UUID(user["id"]),
        )
    except dispatch_svc.DispatchBlocked as blocked:
        raise await refusal(session, user, blocked, resource_id=message.id)
    return _out(message)
