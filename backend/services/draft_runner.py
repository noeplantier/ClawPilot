"""Prepares the automatic AI drafts, in the background of the API process (no worker, no Beat to wait for).

When prospects become eligible (an import, an addition from the map, a saved offer, a manual "run") `kick` starts one
sweep per organisation: it records a job per eligible prospect (idempotent), then prepares a bounded number of drafts, a
couple at a time. A draft is a proposal in the usual review flow (status "draft"): nothing is approved, nothing is sent.

Independent by construction: a slow or failing provider only changes the job's state (generating -> ready / failed /
unavailable); the prospect stays on the map and no batch waits for it. A provider limit stops the sweep and the rest
resumes at the next kick or retry. Without a complete offer a job says `offer_required` and nothing is invented.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import Lead
from db.session import AsyncSessionLocal
from repositories import audit_repo, draft_job_repo, draft_repo, prospect_repo, usage_repo
from services import ai_svc, feature_flags
from services.outreach_os import ai_draft
from services.outreach_os import drafts as drafts_svc
from services.outreach_os import email_footer
from services.outreach_os import heat as heat_rules
from services.outreach_os.types import SignalState
from services.outreach_os.unsubscribe import make_token

logger = logging.getLogger(__name__)

CANDIDATES = 40  # prospects looked at per sweep
BATCH_BUDGET = 10  # drafts prepared per sweep (the provider's free limit is not ours to spend)
CONCURRENCY = 2  # drafts in flight at once
_running: set[uuid.UUID] = set()
_background: set[asyncio.Task[None]] = set()

Generator = Callable[[list[dict[str, str]]], Awaitable[dict[str, Optional[str]]]]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _public_base_url() -> str:
    return os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")


async def _context(
    session: AsyncSession, lead: Lead, offer: dict[str, str]
) -> tuple[ai_draft.DraftContext, str, str, Any]:
    """(what the message may use, the data fingerprint, the language, the latest source) for one prospect."""
    sources = await prospect_repo.sources_of(session, lead.id)
    latest = max(sources, key=lambda s: s.fetched_at) if sources else None
    results = await prospect_repo.effective_results(session, lead.id)  # a dismissed signal is never stated
    detected = {r.key: r.evidence for r in results if r.state is SignalState.DETECTED}
    raw_updated = (latest.fields.get("last_updated") if latest else None) or None
    last_updated = date.fromisoformat(raw_updated) if isinstance(raw_updated, str) else None
    lines = drafts_svc.observed_facts(results, latest.source_name if latest else "", last_updated)
    state = ai_draft.site_state(website=lead.website if heat_rules.is_known(lead.website) else None, detected=detected)
    # "no website listed" is told by the one established sentence of the web statement, not as a second observation
    facts = ai_draft.facts_from([(key, sentence) for key, sentence in lines if key != "no_website"])
    language = "fr" if (lead.country or "").upper() == "FR" else offer["language"]
    ctx = ai_draft.DraftContext(
        name=lead.full_name,
        activity=lead.vertical if heat_rules.is_known(lead.vertical) else None,
        city=lead.city if heat_rules.is_known(lead.city) else None,
        state=state,
        facts=facts,
        language=language,
    )
    data = ai_draft.fingerprint(
        {
            "name": ctx.name,
            "activity": ctx.activity,
            "city": ctx.city,
            "state": state,
            "facts": list(facts),
            "source": str(latest.id) if latest else None,
        }
    )
    return ctx, data, language, latest


def _key(account_id: uuid.UUID, lead_id: uuid.UUID, offer: str, language: str, data: str) -> str:
    return ai_draft.idempotency_key(
        account_id=str(account_id),
        lead_id=str(lead_id),
        channel="email",
        offer=offer,
        language=language,
        template=ai_draft.TEMPLATE_VERSION,
        data=data,
    )


async def record_jobs(
    session_factory: async_sessionmaker[AsyncSession], account_id: uuid.UUID, now: datetime
) -> dict[str, int]:
    """Step 1: one job per eligible prospect whose draft is not already prepared (same key: nothing is redone)."""
    created = {"queued": 0, "offer_required": 0}
    async with session_factory() as session:
        offer = ai_draft.valid_offer(await draft_job_repo.offer_of(session, account_id))
        offer_key = ai_draft.offer_hash(offer)
        for lead_id in await draft_job_repo.candidates(session, account_id, offer_key, CANDIDATES, now):
            lead = await session.get(Lead, lead_id)
            if lead is None:
                continue
            ctx, data, language, _ = await _context(session, lead, offer or {"language": "fr"})
            status = "queued" if offer else "offer_required"
            if await draft_job_repo.create(
                session,
                account_id,
                lead_id,
                key=_key(account_id, lead_id, offer_key, language, data),
                offer=offer_key,
                language=language,
                site_state=ctx.state,
                status=status,
            ):
                created[status] += 1
        await session.commit()
    return created


async def run_job(
    session_factory: async_sessionmaker[AsyncSession],
    account_id: uuid.UUID,
    job_id: uuid.UUID,
    *,
    generator: Generator,
    now: Callable[[], datetime],
) -> str:
    """Step 2, one job: claim it, ask the provider, check the answer, store the draft. Returns the job's new status."""
    async with session_factory() as session:
        job = await draft_job_repo.claim(session, job_id, now())
        if job is None:
            return "skipped"
        lead_id, key = job.lead_id, job.idempotency_key
        await session.commit()

    async def end(status: str, **kw: Any) -> str:
        async with session_factory() as s:
            await draft_job_repo.finish(s, job_id, status=status, now=now(), **kw)
            await s.commit()
        return status

    try:
        async with session_factory() as session:
            offer = ai_draft.valid_offer(await draft_job_repo.offer_of(session, account_id))
            lead = await prospect_repo.get(session, account_id, str(lead_id))
            if offer is None:
                return await end("offer_required", error_code="offer_required", error="Configure your offer first.")
            if lead is None:
                return await end("failed", error_code="prospect_gone", error="The prospect is no longer available.")
            ctx, _, _, latest = await _context(session, lead, offer)
            sender = drafts_svc.SenderIdentity.from_env()
            if sender is None:
                return await end(
                    "unavailable",
                    error_code="sender_not_configured",
                    error="Sender identity is not configured (OUTREACH_SENDER_NAME, _COMPANY, _ADDRESS, _EMAIL).",
                )
            from deps import JWT_SECRET  # the unsubscribe link is signed with the same secret as everywhere else

            footer = email_footer.render_footer(
                name=sender.name,
                company=sender.company,
                postal_address=sender.postal_address,
                source=f"annuaire « {latest.source_name} »" if latest else None,
                unsubscribe_url=f"{_public_base_url()}/api/unsubscribe/{make_token(JWT_SECRET, account_id, lead.id)}",
                reply_to=sender.reply_to,
                whatsapp=sender.whatsapp,
            )
            business, messages = lead.full_name, ai_draft.build_messages(ctx, offer)

        try:
            answer = await generator(messages)
        except ai_svc.AIUnavailable as exc:
            limited = exc.code == "ai_rate_limited"
            return await end(
                "unavailable" if limited or exc.code == "ai_not_configured" else "failed",
                error_code=exc.code,
                error=exc.message,
            )

        found = ai_draft.problems(answer, ctx)
        if found:  # fail closed: a doubtful proposal is dropped, the prospect and the batch are untouched
            return await end(
                "failed",
                error_code="draft_rejected",
                error="The proposal was dropped by the safety checks ("
                + ", ".join(found)
                + "). Write it yourself or retry.",
            )
        body = f"{(answer['body'] or '').strip()}\n\n{footer}"
        broken = drafts_svc.compliance_problems(body, sender)
        if broken:
            return await end("failed", error_code="not_compliant", error="Not compliant: " + ", ".join(broken))
        async with session_factory() as session:
            draft, created = await draft_repo.create_idempotent(
                session,
                account_id,
                idempotency_key=key,
                lead_id=lead_id,
                channel="email",
                subject=(answer["subject"] or "").strip(),
                body=body,
                facts=list(ctx.facts),
                template_version=ai_draft.TEMPLATE_VERSION,
                status="draft",
                dry_run=feature_flags.dry_run(),
                created_by_user_id=None,
            )  # the same key returns the existing draft: a validated or hand-edited one is never overwritten
            if created:
                await usage_repo.record(session, account_id, "drafts_generated", 1)
                await audit_repo.log(
                    session,
                    account_id,
                    action="draft.created",
                    resource_type="draft",
                    resource_id=draft.id,
                    diff={
                        "prospect_id": str(lead_id),
                        "auto": True,
                        "site_state": ctx.state,
                        "business": business[:80],
                    },
                )
            await draft_job_repo.finish(session, job_id, status="ready", now=now(), draft_id=draft.id)
            await session.commit()
        return "ready"
    except Exception as exc:  # noqa: BLE001 (a job must end in a state, never stay generating)
        logger.warning("draft_job job_id=%s failed: %s", job_id, type(exc).__name__)
        return await end("failed", error_code="internal_error", error="The draft could not be prepared. Retry later.")


async def prepare(
    account_id: uuid.UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    generator: Optional[Generator] = None,
    now: Callable[[], datetime] = utcnow,
) -> dict[str, int]:
    """One sweep: record the jobs, then prepare up to BATCH_BUDGET of them, CONCURRENCY at a time. Never raises."""
    started = time.monotonic()
    run = generator or ai_svc.complete
    out = {"queued": 0, "offer_required": 0, "ready": 0, "failed": 0, "unavailable": 0, "skipped": 0}
    try:
        out.update(await record_jobs(session_factory, account_id, now()))
        async with session_factory() as session:
            ids = await draft_job_repo.due(session, account_id, BATCH_BUDGET, now())
        gate = asyncio.Semaphore(CONCURRENCY)
        limited = asyncio.Event()

        async def one(job_id: uuid.UUID) -> None:
            async with gate:
                if limited.is_set():  # the provider's limit is reached: the rest waits for the next sweep
                    return
                status = await run_job(session_factory, account_id, job_id, generator=run, now=now)
                out[status] = out.get(status, 0) + 1
                if status == "unavailable":
                    limited.set()

        await asyncio.gather(*(one(i) for i in ids))
    except Exception as exc:  # noqa: BLE001
        logger.warning("draft_sweep account_id=%s failed: %s", account_id, type(exc).__name__)
    logger.info(
        "draft_sweep account_id=%s duration_ms=%d %s",
        account_id,
        int((time.monotonic() - started) * 1000),
        " ".join(f"{k}={v}" for k, v in out.items()),
    )
    return out


def kick(account_id: uuid.UUID) -> None:
    """Start a sweep for this organisation in the background (one at a time per organisation). Call after the data is
    committed. Nothing waits for it."""
    if account_id in _running:
        return
    _running.add(account_id)

    async def go() -> None:
        try:
            await prepare(account_id)
        finally:
            _running.discard(account_id)

    task = asyncio.get_running_loop().create_task(go())
    _background.add(task)
    task.add_done_callback(_background.discard)
