"""Send limits: daily cap, rolling hourly cap, minimum delay between messages. Pure, clock injected."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SendLimits:
    max_per_day: int
    max_per_hour: int
    min_delay_seconds: int


@dataclass(frozen=True)
class LimitDecision:
    allowed: bool
    code: str | None = None  # "daily" | "hourly" | "delay"
    reason: str | None = None
    retry_at: datetime | None = None


def evaluate(limits: SendLimits, dispatched_today: list[datetime], now: datetime, day_end: datetime) -> LimitDecision:
    """Decide whether one more message may go out now.

    `dispatched_today` holds the dispatch times since the start of the account's current day. The most
    restrictive limit is reported; a daily block waits for `day_end` (the next local midnight).
    """
    if len(dispatched_today) >= limits.max_per_day:
        return LimitDecision(False, "daily", f"daily limit of {limits.max_per_day} reached", day_end)

    window_start = now - timedelta(hours=1)
    last_hour = sorted(t for t in dispatched_today if t > window_start)
    if len(last_hour) >= limits.max_per_hour:
        retry = (
            (last_hour[len(last_hour) - limits.max_per_hour] + timedelta(hours=1)) if limits.max_per_hour else day_end
        )
        return LimitDecision(False, "hourly", f"hourly limit of {limits.max_per_hour} reached", retry)

    if dispatched_today and limits.min_delay_seconds > 0:
        next_ok = max(dispatched_today) + timedelta(seconds=limits.min_delay_seconds)
        if now < next_ok:
            return LimitDecision(
                False, "delay", f"minimum delay of {limits.min_delay_seconds}s between messages", next_ok
            )
    return LimitDecision(True)
