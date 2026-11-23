"""Is the sending mailbox really being read? A bounded automatic mode must not run blind: an opposition or a reply that
arrives and is not read would not stop the next message.

The worker records the time of each successful inbox poll (tasks/inbox_tasks.py); this module only answers from that
record. No record, or an old one, means "not read"."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from celery_app import REDIS_BROKER_URL

KEY = "outreachos:health:inbox-last-ok"
TTL_SECONDS = 3600
MAX_AGE_SECONDS = 1200  # the poll runs every 5 minutes: three missed polls in a row is "not read"


def client() -> Any:
    import redis

    return redis.Redis.from_url(REDIS_BROKER_URL, socket_connect_timeout=2, socket_timeout=2)


def record_ok(redis_client: Any, now: Optional[datetime] = None) -> None:
    redis_client.set(KEY, (now or datetime.now(timezone.utc)).isoformat(), ex=TTL_SECONDS)


def age_seconds(redis_client: Any, now: Optional[datetime] = None) -> Optional[int]:
    raw = redis_client.get(KEY)
    if not raw:
        return None
    try:
        at = datetime.fromisoformat(raw.decode("utf-8") if isinstance(raw, bytes) else str(raw))
    except ValueError:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return max(0, int(((now or datetime.now(timezone.utc)) - at).total_seconds()))


def is_reading(configured: bool, age: Optional[int]) -> bool:
    """Replies are read only if a mailbox is configured AND it was read successfully a short while ago."""
    return bool(configured and age is not None and age <= MAX_AGE_SECONDS)


def reading_now(configured: bool) -> bool:
    """Convenience for a process that can reach Redis; an unreachable Redis is "not read", never "read"."""
    if not configured:
        return False
    try:
        c = client()
        try:
            return is_reading(True, age_seconds(c))
        finally:
            c.close()
    except Exception:  # noqa: BLE001 (no answer is not "all is well")
        return False
