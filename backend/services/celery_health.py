"""Secret-free worker, Beat-schedule and automation-queue snapshot."""

from __future__ import annotations

from datetime import datetime, timezone

import redis

from celery_app import REDIS_BROKER_URL, celery_app
from tasks.health_tasks import BEAT_HEARTBEAT_KEY


def snapshot(now: datetime | None = None) -> dict:
    checked_at = now or datetime.now(timezone.utc)
    workers: dict[str, list] = {}
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        pings = inspector.ping() or {}
        active_queues = inspector.active_queues() or {}
        workers = {name: [queue.get("name") for queue in queues] for name, queues in active_queues.items()}
        worker_count = len(pings)
    except Exception:  # noqa: BLE001 - health must report an unavailable broker without exposing its address.
        worker_count = 0

    client = redis.Redis.from_url(REDIS_BROKER_URL, socket_connect_timeout=1, socket_timeout=1)
    try:
        client.ping()
        queue_depth = int(client.llen("automation"))
        raw_beat = client.get(BEAT_HEARTBEAT_KEY)
    except Exception:  # noqa: BLE001 - return unknown/unavailable without connection details.
        queue_depth = None
        raw_beat = None
        broker_ok = False
    else:
        broker_ok = True
    finally:
        client.close()

    last_beat = None
    if raw_beat:
        try:
            last_beat = datetime.fromisoformat(raw_beat.decode("utf-8"))
            if last_beat.tzinfo is None:
                last_beat = last_beat.replace(tzinfo=timezone.utc)
        except (UnicodeDecodeError, ValueError):
            last_beat = None
    beat_age = max(0, int((checked_at - last_beat).total_seconds())) if last_beat else None
    automation_active = any("automation" in queues for queues in workers.values())
    beat_active = bool(beat_age is not None and beat_age <= 180)
    return {
        "checked_at": checked_at,
        "broker_ok": broker_ok,
        "worker": {
            "ok": worker_count > 0,
            "active_count": worker_count,
            "automation_queue": automation_active,
            "checked_at": checked_at,
        },
        "beat": {
            "ok": beat_active,
            "last_tick_at": last_beat,
            "age_seconds": beat_age,
            "checked_at": checked_at,
        },
        "automation_queue": {"pending": queue_depth, "checked_at": checked_at},
    }
