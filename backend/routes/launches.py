"""Individual campaigns: one personalised, approved message per recipient, planned and sent one by one.

Reading is open to any member; creating a selection, generating drafts, approving, planning and cancelling need
owner/admin, like every other sending action. Nothing here sends a message: "schedule" writes the plan, the scheduled
task (tasks/campaign_tasks.py) sends each message later through the common dispatch, every gate checked again.
See docs/campaign-launch.md.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Campaign
from db.session import get_db_session
from deps import get_current_user, require_roles
from models import (
    LaunchCreatedOut,
    LaunchCreateIn,
    LaunchExcludedOut,
    LaunchGatesOut,
    LaunchOut,
    LaunchOverviewOut,
    LaunchPlanOut,
    LaunchProviderOut,
    LaunchReviewIn,
    LaunchReviewPageOut,
    LaunchRowOut,
    LaunchScheduleIn,
    LaunchTopUpIn,
    LaunchTrackingOut,
    LaunchTrackingRowOut,
)
from repositories import campaign_repo, draft_job_repo, launch_repo
from services import campaign_launch
from services.outreach_os import campaign_plan

router = APIRouter(prefix="/launches", tags=["launches"])
decider = require_roles("owner", "admin")


def _account(user: dict) -> uuid.UUID:
    return uuid.UUID(user["org_id"])


def _uid(user: dict) -> uuid.UUID:
    return uuid.UUID(user["id"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _launch(session: AsyncSession, user: dict, launch_id: str) -> Campaign:
    campaign = await campaign_repo.get_campaign(session, _account(user), launch_id)
    if campaign is None or campaign.kind != "individual":
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


async def _scheduler_health() -> dict[str, Any]:
    """Whether a worker and the Beat are seen. The plan is only sent while they run: the screen says so instead of
    hoping."""
    try:
        from services import celery_health

        snap = await asyncio.wait_for(asyncio.to_thread(celery_health.snapshot), timeout=4)
    except Exception:  # noqa: BLE001 (an unreachable broker is an answer: "not seen", never an error page)
        return {"checked": False, "worker_ok": False, "beat_ok": False, "broker_ok": False}
    return {
        "checked": True,
        "worker_ok": bool(snap["worker"]["ok"]),
        "beat_ok": bool(snap["beat"]["ok"]),
        "broker_ok": bool(snap["broker_ok"]),
        "beat_age_seconds": snap["beat"]["age_seconds"],
    }


def _gates_out(g: dict[str, Any], scheduler: Optional[dict[str, Any]] = None) -> LaunchGatesOut:
    p = g["provider"]
    policy = g["policy"]
    return LaunchGatesOut(
        provider=LaunchProviderOut(
            id=p.id, label=p.label, host=p.host, cold_outreach=p.cold_outreach, restriction=p.restriction
        ),
        dry_run=g["dry_run"],
        live=g["live"],
        kill_switch=g["kill_switch"],
        paused=g["paused"],
        sandbox=g["sandbox"],
        allowlist_size=g["allowlist_size"],
        sender_configured=g["sender_configured"],
        smtp_complete=g["smtp_complete"],
        max_per_day=g["limits"].max_per_day,
        max_per_hour=g["limits"].max_per_hour,
        min_delay_seconds=g["limits"].min_delay_seconds,
        window_start_hour=policy.window_start_hour,
        window_end_hour=policy.window_end_hour,
        timezone=policy.account_default_timezone,
        timezone_source=policy.timezone_source,
        sent_today=g["sent_today"],
        sent_last_hour=g["sent_last_hour"],
        next_allowed_at=g["next_allowed_at"],
        scheduler=scheduler or {},
    )


def _launch_out(campaign: Campaign, recipients: int, dispatch: dict[str, int]) -> LaunchOut:
    return LaunchOut(
        id=str(campaign.id),
        name=campaign.name,
        status=campaign.status,
        created_at=campaign.created_at,
        recipients=recipients,
        planned=dispatch.get("scheduled", 0) + dispatch.get("sending", 0),
        sent=dispatch.get("accepted", 0),
    )


def _excluded_out(item: campaign_launch.Excluded) -> LaunchExcludedOut:
    return LaunchExcludedOut(
        lead_id=str(item.lead_id), name=item.name, city=item.city, email=item.email, code=item.code, label=item.label
    )


def _row_out(state: campaign_launch.LeadState) -> LaunchRowOut:
    lead, draft, job = state.lead, state.draft, state.job
    source = state.source
    return LaunchRowOut(
        lead_id=str(state.lead_id),
        name=lead.full_name if lead else "(supprimé)",
        city=lead.city if lead else None,
        email=lead.email if lead else None,
        stage=state.stage,
        exclusion=(
            {"code": state.exclusion, "label": campaign_plan.exclusion_label(state.exclusion)}
            if state.exclusion
            else None
        ),
        draft=(
            {
                "id": str(draft.id),
                "status": draft.status,
                "subject": draft.subject,
                "body": draft.body,
                "edited": draft.edited_at is not None,
                "auto": draft.created_by_user_id is None,
                "created_at": draft.created_at,
            }
            if draft
            else None
        ),
        draft_job=({"status": job.status, "error_code": job.error_code, "error": job.error} if job else None),
        evidence={
            "facts": list(draft.facts or []) if draft else [],
            "site_state": state.site_state,
            "source": (
                {"name": source["name"], "url": source["url"], "fetched_at": source["fetched_at"]} if source else None
            ),
        },
        authorization={
            "ok": state.authorization.ok,
            "basis": state.authorization.basis,
            "label": state.authorization.label,
            "code": state.authorization.code,
        },
        problems=[{"code": p.code, "label": p.label, "blocking": p.blocking} for p in state.problems],
        dispatch=(
            {
                "status": state.dispatch.status,
                "planned_at": state.dispatch.planned_at,
                "reason": state.dispatch.last_reason,
            }
            if state.dispatch
            else None
        ),
    )


def _labels(codes: dict[str, int]) -> dict[str, str]:
    return {code: campaign_plan.exclusion_label(code) for code in codes}


# ---------------------------------------------------------------- provider and gates
@router.get("/provider", response_model=LaunchGatesOut)
async def provider(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    """The active provider, what it forbids, the limits, the window, whether a worker is seen: read before planning."""
    gates = await campaign_launch.gates(session, _account(user), _now())
    return _gates_out(gates, await _scheduler_health())


# ---------------------------------------------------------------- selection
@router.get("", response_model=list[LaunchOut])
async def list_launches(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    account_id = _account(user)
    out = []
    for campaign in await launch_repo.launches(session, account_id):
        recipients = len(await launch_repo.selection_of(session, account_id, campaign.id))
        out.append(_launch_out(campaign, recipients, await launch_repo.counts(session, account_id, campaign.id)))
    return out


@router.post("", response_model=LaunchCreatedOut)
async def create_launch(
    payload: LaunchCreateIn, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    """Pick up to 100 distinct establishments (valid e-mail, validated, qualified, allowed on the active provider) and
    keep the reason for every prospect passed over. The campaign stays a draft: nothing is planned, nothing is sent."""
    campaign, selection = await campaign_launch.create_launch(
        session, _account(user), _uid(user), name=payload.name.strip(), size=payload.size, now=_now()
    )
    return LaunchCreatedOut(
        launch=_launch_out(campaign, len(selection.picked), {}),
        requested=payload.size,
        selected=len(selection.picked),
        scanned=selection.scanned,
        not_approved=selection.not_approved,
        excluded=[_excluded_out(item) for item in selection.excluded[:300]],
    )


@router.post("/{launch_id}/top-up", response_model=LaunchCreatedOut)
async def top_up(
    launch_id: str,
    payload: LaunchTopUpIn,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Complete the selection to `size` recipients with new distinct establishments (the ones already held are kept)."""
    campaign = await _launch(session, user, launch_id)
    selection = await campaign_launch.top_up(
        session, _account(user), _uid(user), campaign, size=payload.size, now=_now()
    )
    held = await launch_repo.selection_of(session, _account(user), campaign.id)
    return LaunchCreatedOut(
        launch=_launch_out(campaign, len(held), await launch_repo.counts(session, _account(user), campaign.id)),
        requested=payload.size,
        selected=len(selection.picked),
        scanned=selection.scanned,
        not_approved=selection.not_approved,
        excluded=[_excluded_out(item) for item in selection.excluded[:300]],
    )


@router.get("/{launch_id}", response_model=LaunchOverviewOut)
async def overview(
    launch_id: str, user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)
):
    account_id = _account(user)
    campaign = await _launch(session, user, launch_id)
    states = await campaign_launch.evaluate(session, account_id, campaign, _now())
    dispatch = await launch_repo.counts(session, account_id, campaign.id)
    jobs: dict[str, int] = {}
    for state in states:
        if state.job is not None and state.stage == "no_draft":
            jobs[state.job.status] = jobs.get(state.job.status, 0) + 1
    exclusions = campaign_launch.exclusion_counts(states)
    gates = await campaign_launch.gates(session, account_id, _now())
    return LaunchOverviewOut(
        launch=_launch_out(campaign, len(states), dispatch),
        stages=campaign_launch.stage_counts(states),
        exclusions=exclusions,
        exclusion_labels=_labels(exclusions),
        dispatch=dispatch,
        draft_jobs=jobs,
        gates=_gates_out(gates, await _scheduler_health()),
    )


# ---------------------------------------------------------------- drafts and review
@router.post("/{launch_id}/drafts", status_code=202)
async def generate_drafts(
    launch_id: str, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)
):
    """Prepare, in the background, the AI draft of every recipient that has none (the existing flow, scoped: same
    offer, same safety checks, same idempotency). A draft is a proposal: nothing is approved, nothing is sent."""
    account_id = _account(user)
    campaign = await _launch(session, user, launch_id)
    offer = await draft_job_repo.offer_of(session, account_id)
    states = await campaign_launch.evaluate(session, account_id, campaign, _now())
    missing = [s.lead_id for s in states if s.stage == "no_draft"]
    if not offer:
        raise HTTPException(
            status_code=409, detail="Describe your offer first (Pilotage > Offre): no draft is invented without it"
        )
    await session.commit()  # the sweep reads committed data
    started = campaign_launch.generate_missing_drafts(account_id, missing) if missing else False
    return {"missing": len(missing), "started": started, "already_running": bool(missing) and not started}


@router.get("/{launch_id}/review", response_model=LaunchReviewPageOut)
async def review(
    launch_id: str,
    stage: Optional[str] = Query(
        default=None, pattern="^(excluded|no_draft|to_review|rejected|blocked|ready|planned|launched)$"
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Each recipient with what a person needs before approving: address, subject, body, the evidence it uses, the
    authorization of the channel, the errors that block it and the state of its draft."""
    campaign = await _launch(session, user, launch_id)
    states = await campaign_launch.evaluate(session, _account(user), campaign, _now())
    if stage:
        states = [s for s in states if s.stage == stage]
    return LaunchReviewPageOut(total=len(states), items=[_row_out(s) for s in states[offset : offset + limit]])


@router.post("/{launch_id}/review-drafts")
async def review_drafts(
    launch_id: str,
    payload: LaunchReviewIn,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Approve or reject drafts of this campaign. An approval is refused, with the reason, for a draft that has a
    blocker."""
    campaign = await _launch(session, user, launch_id)
    try:
        ids = [uuid.UUID(i) for i in payload.draft_ids]
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid draft id")
    results = await campaign_launch.review_drafts(
        session, _account(user), _uid(user), campaign, ids, payload.decision, _now()
    )
    return {
        "results": results,
        "done": sum(1 for r in results if r["ok"]),
        "refused": sum(1 for r in results if not r["ok"]),
    }


# ---------------------------------------------------------------- plan
async def _plan_out(
    session: AsyncSession, user: dict, campaign: Campaign, scheduled: Optional[int] = None
) -> LaunchPlanOut:
    plan, _, _ = await campaign_launch.preview(session, _account(user), campaign, _now())
    return _plan_dict_out(plan, scheduled)


def _plan_dict_out(plan: dict[str, Any], scheduled: Optional[int] = None) -> LaunchPlanOut:
    return LaunchPlanOut(
        selected=plan["selected"],
        sendable=plan["sendable"],
        stages=plan["stages"],
        exclusions=plan["exclusions"],
        exclusion_labels=_labels(plan["exclusions"]),
        schedule=plan["schedule"],
        blockers=plan["blockers"],
        warnings=plan["warnings"],
        gates=_gates_out(plan["gates"]),
        generated_at=plan["generated_at"],
        scheduled=scheduled,
    )


@router.get("/{launch_id}/plan", response_model=LaunchPlanOut)
async def plan(launch_id: str, user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    """What "Planifier les messages approuvés" would do right now: how many are really sendable, the exclusions, the
    schedule (first and last send, per day), and what blocks or warns. Computed from the data, never from what a
    screen showed.
    """
    return await _plan_out(session, user, await _launch(session, user, launch_id))


@router.post("/{launch_id}/schedule", response_model=LaunchPlanOut)
async def schedule(
    launch_id: str,
    payload: LaunchScheduleIn,
    user: dict = Depends(decider),
    session: AsyncSession = Depends(get_db_session),
):
    """Plan the approved messages: one row per recipient, at the earliest time it may leave, inside the send window and
    the limits. Sends nothing. `expected_count` is the number the person was shown: if the real number differs,
    nothing is planned and the answer says so (409), so a button is never pressed on stale information."""
    campaign = await _launch(session, user, launch_id)
    try:
        result = await campaign_launch.schedule(
            session, _account(user), _uid(user), campaign, expected=payload.expected_count, now=_now()
        )
    except campaign_launch.PlanChanged as changed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "plan_changed",
                "message": f"{changed.actual} messages are sendable now, not {payload.expected_count}: "
                "read the plan again",
                "actual": changed.actual,
            },
        )
    if result.get("refused"):
        blocker = result["blockers"][0]
        raise HTTPException(status_code=409, detail={"code": blocker["code"], "message": blocker["label"]})
    return _plan_dict_out(result, result["scheduled"])


@router.post("/{launch_id}/cancel")
async def cancel(launch_id: str, user: dict = Depends(decider), session: AsyncSession = Depends(get_db_session)):
    """Stop everything that has not left: planned messages are cancelled and the campaign is paused. What already left
    cannot be recalled."""
    campaign = await _launch(session, user, launch_id)
    cancelled = await campaign_launch.cancel(session, _account(user), _uid(user), campaign, _now())
    return {"cancelled": cancelled, "status": campaign.status}


# ---------------------------------------------------------------- tracking
@router.get("/{launch_id}/tracking", response_model=LaunchTrackingOut)
async def tracking(
    launch_id: str,
    state: Optional[str] = Query(default=None, pattern="^[a-z_]{3,20}$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Honest tracking: planned / accepted by SMTP / simulated / failed / reply / opposition / bounce / stopped. A
    message is never called delivered: nothing in the system observes a delivery."""
    campaign = await _launch(session, user, launch_id)
    counts, rows, total = await campaign_launch.tracking(
        session, _account(user), campaign, state=state, offset=offset, limit=limit
    )
    return LaunchTrackingOut(
        counts=counts,
        labels=campaign_plan.TRACKING_LABELS,
        total=total,
        items=[
            LaunchTrackingRowOut(
                lead_id=str(r["lead_id"]),
                name=r["name"],
                city=r["city"],
                email=r["email"],
                state=r["state"],
                label=r["label"],
                reason=r["reason"],
                planned_at=r["planned_at"],
                dispatched_at=r["dispatched_at"],
                adapter=r["adapter"],
                dry_run=r["dry_run"],
            )
            for r in rows
        ],
    )
