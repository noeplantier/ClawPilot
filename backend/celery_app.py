"""Celery application — replaces services/scheduler.py's in-process asyncio
poll loop with a real distributed task queue (plan doc: Celery/Redis section).

Three queues, not one, because the brief requires per-channel throttling: a
burst of campaign sends must never delay processing of inbound webhooks (an
opt-out STOP reply needs to land fast for compliance), so sends/automation/
webhooks are isolated from each other.

Celery workers are synchronous; every task here is a thin `asyncio.run(...)`
wrapper around the same async repositories the FastAPI routes use (see
tasks/_bridge.py), rather than a second, parallel data-access layer.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

REDIS_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
REDIS_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "outreachos",
    broker=REDIS_BROKER_URL,
    backend=REDIS_RESULT_BACKEND,
    # Explicit, not autodiscover_tasks(["tasks"]) — that call looks for a
    # `tasks` *submodule inside* each listed package (Django app convention),
    # not a top-level `tasks` package like this one.
    include=["tasks.send_tasks", "tasks.automation_tasks", "tasks.webhook_tasks", "tasks.inbox_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_routes={
        "tasks.send_tasks.*": {"queue": "sends"},
        "tasks.automation_tasks.*": {"queue": "automation"},
        "tasks.webhook_tasks.*": {"queue": "webhooks"},
        "tasks.inbox_tasks.*": {"queue": "webhooks"},
    },
    beat_schedule={
        # Safety net for apply_async(eta=...) sends that got lost (e.g. a
        # worker restart past the broker's visibility timeout) — see
        # tasks/automation_tasks.py::advance_due_campaign_steps.
        "advance-due-campaign-steps": {
            "task": "tasks.automation_tasks.advance_due_campaign_steps",
            "schedule": 30.0,
            "options": {"queue": "automation"},
        },
        "rescore-all-active-leads": {
            "task": "tasks.automation_tasks.rescore_all_active_leads",
            "schedule": crontab(hour=3, minute=0),
            "options": {"queue": "automation"},
        },
        "stop-unqualified-sequences": {
            "task": "tasks.automation_tasks.stop_unqualified_sequences",
            "schedule": crontab(hour=4, minute=0),
            "options": {"queue": "automation"},
        },
        "reactivate-dormant-leads": {
            "task": "tasks.automation_tasks.reactivate_dormant_leads",
            "schedule": crontab(hour=5, minute=0),
            "options": {"queue": "automation"},
        },
        # No separate "requeue window-blocked sends" beat entry: send_tasks.py's
        # window check uses `self.retry(eta=..., max_retries=None)`, so Celery
        # itself already reschedules those — a second sweep would be redundant.
        # Replies and bounces from the sending mailbox (no-op without IMAP_*): an opt-out must land fast.
        "poll-inbox": {
            "task": "tasks.inbox_tasks.poll_inbox",
            "schedule": 300.0,
            "options": {"queue": "webhooks"},
        },
        "retry-unprocessed-webhooks": {
            "task": "tasks.webhook_tasks.retry_unprocessed_webhooks",
            "schedule": 300.0,
            "options": {"queue": "webhooks"},
        },
    },
)
