"""Outbound dispatch (dry-run): send an approved draft through a channel adapter, under limits and a kill switch.

Nothing here reaches a real provider: the only adapter is the dry-run one, and enabling live sending without a
real adapter is refused. Reading is open to any member; dispatching, simulating events and changing limits
need owner/admin. Refused attempts are written to the audit log (committed before the 4xx is returned).
"""

from __future__ import annotations

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
    LimitsOut,
    LimitsPatch,
    OutboundEventOut,
    OutboundMessageDetail,
    OutboundMessageOut,
    SendStatusOut,
    SimulateIn,
)
from repositories import audit_repo, draft_repo, outbound_repo, send_policy_repo
from services.outreach_os import dispatch as dispatch_svc

router = APIRouter(prefix="/outbound", tags=["outbound"])
decider = require_roles("owner", "admin")

_STATUS_FOR_CODE = {
    "kill_switch": 423,
    "paused": 423,
    "limit_daily": 429,
    "limit_hourly": 429,
    "limit_delay": 429,
    "live_not_available": 501,
    "not_compliant": 422,
    "sender_not_configured": 409,
}


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


async def _refuse(
    session: AsyncSession, user: dict, blocked: dispatch_svc.DispatchBlocked, resource_id: Optional[uuid.UUID]
) -> HTTPException:
    """Record the refusal durably (get_db_session rolls back on HTTPException), then build the error."""
    await audit_repo.log(
        session,
        _account(user),
        action="dispatch.blocked",
        resource_type="outbound_message",
        resource_id=resource_id,
        actor_user_id=uuid.UUID(user["id"]),
        diff={"code": blocked.code, "retry_at": blocked.retry_at.isoformat() if blocked.retry_at else None},
    )
    await session.commit()
    headers = {}
    if blocked.retry_at:
        wait = max(1, int((blocked.retry_at - datetime.now(timezone.utc)).total_seconds()))
        headers["Retry-After"] = str(wait)
    return HTTPException(
        status_code=_STATUS_FOR_CODE.get(blocked.code, 409),
        detail={
            "code": blocked.code,
            "message": blocked.message,
            "retry_at": blocked.retry_at.isoformat() if blocked.retry_at else None,
        },
        headers=headers or None,
    )


# ---------------------------------------------------------------- status and limits
@router.get("/status", response_model=SendStatusOut)
async def status(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    s = await dispatch_svc.send_status(session, _account(user), datetime.now(timezone.utc))
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
async def get_limits(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return _limits_out(await send_policy_repo.get_policy(session, _account(user), "email"))


@router.put("/limits", response_model=LimitsOut)
async def put_limits(
    payload: LimitsPatch, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    """Change the limits and/or pause sending for this organisation (`sending_paused` is the account kill switch)."""
    changes = payload.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to change")
    await send_policy_repo.update_limits(session, _account(user), "email", **changes)
    await audit_repo.log(
        session,
        _account(user),
        action="send_limits.changed",
        resource_type="send_policy",
        actor_user_id=uuid.UUID(user["id"]),
        diff=changes,
    )
    return _limits_out(await send_policy_repo.get_policy(session, _account(user), "email"))


# ---------------------------------------------------------------- dispatch
@router.post("/dispatch", response_model=OutboundMessageOut)
async def dispatch(
    payload: DispatchIn,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=200),
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Dry-run dispatch of an approved draft. A draft yields at most one message; same key ⇒ same message."""
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
        )
    except dispatch_svc.DispatchBlocked as blocked:
        raise await _refuse(session, user, blocked, draft.id)
    return _out(message, created)


# ---------------------------------------------------------------- history
@router.get("", response_model=list[OutboundMessageOut])
async def list_messages(
    status: Optional[str] = Query(default=None, pattern="^(sent|failed|bounced|replied)$"),
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
        raise await _refuse(session, user, blocked, message.id)
    return _out(message)
