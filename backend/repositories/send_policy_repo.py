"""Per-account, per-channel throttle + send-window policy (plan doc: Celery
architecture section). No row yet for an account/channel just means "use the
built-in defaults" — accounts don't need to provision a policy up front.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import SendPolicy

DEFAULT_MAX_PER_HOUR = 100
DEFAULT_WINDOW_START_HOUR = 8
DEFAULT_WINDOW_END_HOUR = 18
DEFAULT_MAX_PER_DAY = 20  # conservative: a new account must not be able to blast by default
DEFAULT_MIN_DELAY_SECONDS = 60


@dataclass
class EffectivePolicy:
    max_per_hour: int = DEFAULT_MAX_PER_HOUR
    window_start_hour: int = DEFAULT_WINDOW_START_HOUR
    window_end_hour: int = DEFAULT_WINDOW_END_HOUR
    timezone_source: str = "lead_country"
    account_default_timezone: str = "UTC"
    max_per_day: int = DEFAULT_MAX_PER_DAY
    min_delay_seconds: int = DEFAULT_MIN_DELAY_SECONDS
    sending_paused: bool = False


async def get_policy(session: AsyncSession, account_id: uuid.UUID, channel: str) -> EffectivePolicy:
    result = await session.execute(
        select(SendPolicy).where(SendPolicy.account_id == account_id, SendPolicy.channel == channel)
    )
    row = result.scalar_one_or_none()
    if not row:
        return EffectivePolicy()
    return EffectivePolicy(
        max_per_hour=row.max_per_hour,
        window_start_hour=row.window_start_hour,
        window_end_hour=row.window_end_hour,
        timezone_source=row.timezone_source,
        account_default_timezone=row.account_default_timezone,
        max_per_day=row.max_per_day,
        min_delay_seconds=row.min_delay_seconds,
        sending_paused=row.sending_paused,
    )


LIMIT_FIELDS = ("max_per_day", "max_per_hour", "min_delay_seconds", "sending_paused")


async def update_limits(session: AsyncSession, account_id: uuid.UUID, channel: str, **changes: object) -> SendPolicy:
    """Create the account's policy row on first change, then apply only the given limit fields."""
    row = (
        await session.execute(
            select(SendPolicy).where(SendPolicy.account_id == account_id, SendPolicy.channel == channel)
        )
    ).scalar_one_or_none()
    if row is None:
        row = SendPolicy(account_id=account_id, channel=channel)
        session.add(row)
    for name, value in changes.items():
        if name not in LIMIT_FIELDS:
            raise ValueError(f"not a limit field: {name}")
        setattr(row, name, value)
    await session.flush()
    await session.refresh(row)
    return row


def in_window(policy: EffectivePolicy, local_hour: int) -> bool:
    return policy.window_start_hour <= local_hour < policy.window_end_hour
