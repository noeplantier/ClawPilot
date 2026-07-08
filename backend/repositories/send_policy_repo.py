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


@dataclass
class EffectivePolicy:
    max_per_hour: int = DEFAULT_MAX_PER_HOUR
    window_start_hour: int = DEFAULT_WINDOW_START_HOUR
    window_end_hour: int = DEFAULT_WINDOW_END_HOUR
    timezone_source: str = "lead_country"
    account_default_timezone: str = "UTC"


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
    )


def in_window(policy: EffectivePolicy, local_hour: int) -> bool:
    return policy.window_start_hour <= local_hour < policy.window_end_hour
