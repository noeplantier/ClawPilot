"""Small, provider-free heartbeats used to report the Beat-to-worker path."""

from __future__ import annotations

from datetime import datetime, timezone

import redis

from celery_app import REDIS_BROKER_URL, celery_app

BEAT_HEARTBEAT_KEY = "outreachos:health:celery-beat-last-tick"
BEAT_HEARTBEAT_TTL_SECONDS = 180


@celery_app.task(name="tasks.health_tasks.record_beat_heartbeat")
def record_beat_heartbeat() -> bool:
    client = redis.Redis.from_url(REDIS_BROKER_URL, socket_connect_timeout=2, socket_timeout=2)
    try:
        client.set(BEAT_HEARTBEAT_KEY, datetime.now(timezone.utc).isoformat(), ex=BEAT_HEARTBEAT_TTL_SECONDS)
        return True
    finally:
        client.close()
