"""Beat task: read the sending mailbox over IMAP (replies, hard bounces, STOP). No-op when IMAP is not configured."""

from __future__ import annotations

import logging

from celery_app import celery_app
from services import imap_svc, inbox_health, inbox_sync
from tasks._bridge import run_async

logger = logging.getLogger("outreachos.inbox")


async def _poll_impl(session) -> dict:
    mailbox = imap_svc.mailbox_from_env()
    if mailbox is None:
        return {"status": "not_configured"}
    try:
        return {"status": "ok", **(await inbox_sync.sync(session, mailbox)).as_dict()}
    except Exception as exc:  # network or auth: report the class only, never the credentials
        logger.warning("inbox poll failed (%s)", type(exc).__name__)
        return {"status": "failed", "error": type(exc).__name__}


@celery_app.task(name="tasks.inbox_tasks.poll_inbox")
def poll_inbox() -> dict:
    result = run_async(_poll_impl)
    if (
        result.get("status") == "ok"
    ):  # the proof that replies and oppositions are being read (the automatic mode needs it)
        try:
            c = inbox_health.client()
            try:
                inbox_health.record_ok(c)
            finally:
                c.close()
        except Exception as exc:  # noqa: BLE001 (health bookkeeping must never fail the poll)
            logger.warning("inbox health not recorded (%s)", type(exc).__name__)
    return result
