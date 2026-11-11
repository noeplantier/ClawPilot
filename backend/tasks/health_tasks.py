"""Small, provider-free heartbeats used to report the Beat-to-worker path."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import redis

from celery_app import REDIS_BROKER_URL, celery_app

BEAT_HEARTBEAT_KEY = "outreachos:health:celery-beat-last-tick"
BEAT_HEARTBEAT_TTL_SECONDS = 180
WORKER_CONFIG_KEY = "outreachos:health:worker-send-config"


@celery_app.task(name="tasks.health_tasks.record_beat_heartbeat")
def record_beat_heartbeat() -> bool:
    """Runs IN the worker: the tick proves Beat reaches it, and the fingerprint tells what the worker would do with an
    e-mail (booleans and names only), so the API can warn when its own configuration differs."""
    from services import runtime_config

    client = redis.Redis.from_url(REDIS_BROKER_URL, socket_connect_timeout=2, socket_timeout=2)
    try:
        now = datetime.now(timezone.utc).isoformat()
        client.set(BEAT_HEARTBEAT_KEY, now, ex=BEAT_HEARTBEAT_TTL_SECONDS)
        client.set(
            WORKER_CONFIG_KEY,
            json.dumps({**runtime_config.fingerprint(), "reported_at": now}),
            ex=BEAT_HEARTBEAT_TTL_SECONDS,
        )
        return True
    finally:
        client.close()
