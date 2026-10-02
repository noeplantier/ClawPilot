"""The single enforcement point for outbound sends: kill switch, pause, and send limits.

Every path that can make a message leave the system calls this before the provider: the prospect dispatch
(services/outreach_os/dispatch.py), the single and batch send routes, the campaign step runner and the Celery send
tasks. Never call `sendgrid_svc.send_email` / `twilio_svc.send_whatsapp` from a new path without going through here.

Order: kill switch (environment) → pause of the organisation → daily cap, rolling hourly cap, minimum delay.
Counting is shared: sends from every path (the prospect ledger and the legacy `email_sends` / `whatsapp_sends`)
count toward the same limits, so switching path does not reset them. A per-organisation, per-channel advisory
lock held until the end of the transaction serialises concurrent senders, so parallel requests cannot all pass
the check and overshoot a cap.
"""

from __future__ import annotations

import uuid
import zoneinfo
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from repositories import outbound_repo, send_policy_repo
from services import feature_flags
from services.outreach_os import limits

CHANNELS = ("email", "whatsapp")


class SendBlocked(Exception):
    """A send was refused. `code` is stable and machine-readable; `retry_at` is set when waiting helps."""

    def __init__(self, code: str, message: str, retry_at: Optional[datetime] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_at = retry_at


@dataclass
class SendStatus:
    halted_by_env: bool
    paused: bool
    dry_run: bool
    limits: limits.SendLimits
    sent_today: int
    sent_last_hour: int
    last_dispatched_at: Optional[datetime]
    next_allowed_at: Optional[datetime]
    blocked_by: Optional[str]


def day_bounds(now: datetime, tz_name: str) -> tuple[datetime, datetime]:
    """Start and end (UTC) of the calendar day containing `now` in the organisation's timezone."""
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")
    local = now.astimezone(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


async def _lock(session: AsyncSession, account_id: uuid.UUID, channel: str) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"send:{account_id}:{channel}"}
    )


async def assert_not_halted(session: AsyncSession, account_id: uuid.UUID, channel: str) -> None:
    if feature_flags.kill_switch():
        raise SendBlocked("kill_switch", "Sending is halted by the kill switch (SEND_KILL_SWITCH)")
    if (await send_policy_repo.get_policy(session, account_id, channel)).sending_paused:
        raise SendBlocked("paused", "Sending is paused for this organisation")


async def assert_within_limits(
    session: AsyncSession, account_id: uuid.UUID, channel: str, now: Optional[datetime] = None
) -> None:
    now = now or datetime.now(timezone.utc)
    policy = await send_policy_repo.get_policy(session, account_id, channel)
    day_start, day_end = day_bounds(now, policy.account_default_timezone)
    times = await outbound_repo.dispatch_times_since(session, account_id, channel, day_start)
    decision = limits.evaluate(
        limits.SendLimits(policy.max_per_day, policy.max_per_hour, policy.min_delay_seconds), times, now, day_end
    )
    if not decision.allowed:
        raise SendBlocked(f"limit_{decision.code}", decision.reason or "send limit reached", decision.retry_at)


async def check(session: AsyncSession, account_id: uuid.UUID, channel: str, now: Optional[datetime] = None) -> None:
    """Raise `SendBlocked` unless one more message may leave now. Holds the sender lock until the transaction ends."""
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel: {channel}")
    await _lock(session, account_id, channel)
    await assert_not_halted(session, account_id, channel)
    await assert_within_limits(session, account_id, channel, now)


async def lock_and_assert_not_halted(session: AsyncSession, account_id: uuid.UUID, channel: str) -> None:
    await _lock(session, account_id, channel)
    await assert_not_halted(session, account_id, channel)


async def status(session: AsyncSession, account_id: uuid.UUID, channel: str, now: datetime) -> SendStatus:
    policy = await send_policy_repo.get_policy(session, account_id, channel)
    day_start, day_end = day_bounds(now, policy.account_default_timezone)
    times = await outbound_repo.dispatch_times_since(session, account_id, channel, day_start)
    cfg = limits.SendLimits(policy.max_per_day, policy.max_per_hour, policy.min_delay_seconds)
    decision = limits.evaluate(cfg, times, now, day_end)
    halted, paused = feature_flags.kill_switch(), policy.sending_paused
    blocked_by = "kill_switch" if halted else "paused" if paused else decision.code
    return SendStatus(
        halted_by_env=halted,
        paused=paused,
        dry_run=feature_flags.dry_run(),
        limits=cfg,
        sent_today=len(times),
        sent_last_hour=len([t for t in times if t > now - timedelta(hours=1)]),
        last_dispatched_at=max(times) if times else None,
        next_allowed_at=decision.retry_at,
        blocked_by=blocked_by,
    )
