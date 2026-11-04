"""Automatic AI drafts: prepared when a prospect is eligible and an offer exists, in the background, never blocking.

The provider is a double injected into the runner (no network); everything else is real: PostgreSQL, the eligibility
policy, the draft repository, the footer. A draft is a proposal — nothing here approves or sends anything."""

import asyncio
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests
from prospect_fixtures import insert_rows, row
from sqlalchemy import func, select

from db.models import Account, DraftJob, MessageDraft, OutboundMessage, ProspectSignal, ProspectSource
from repositories import draft_job_repo, draft_repo, prospect_repo
from services import ai_svc, draft_runner
from tasks import _bridge
from tasks._bridge import run_async

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
SF = _bridge._SessionLocal
OFFER = {
    "name": "Site vitrine",
    "pitch": "Un site clair, rapide à publier, avec réservation intégrée.",
    "cta": "Un appel de 15 minutes",
    "language": "fr",
}
GOOD = {
    "subject": "Votre présence en ligne",
    "body": (
        "Bonjour, je me permets de vous écrire au sujet de votre établissement. Nous aidons les restaurateurs de la "
        "région à présenter leur carte et à recevoir des réservations plus simplement, avec une page claire que vos "
        "clients retrouvent facilement depuis leur téléphone. Si cela vous parle, seriez-vous disposé à un court "
        "échange cette semaine pour voir ce qui serait utile chez vous ?"
    ),
}


def _account():
    async def go(session):
        account = Account(name=f"drafts {uuid.uuid4().hex[:8]}")
        session.add(account)
        await session.flush()
        return account.id

    return run_async(go)


def _offer(account, offer=OFFER):
    async def go(session):
        await draft_job_repo.set_offer(session, account, offer)

    run_async(go)


def provider(calls, answer=GOOD, error=None):
    async def generate(messages):
        calls.append(messages)
        if error is not None:
            raise error
        return answer

    return generate


def prepare(account, generator, *, later=0):
    stamp = datetime.now(timezone.utc) + timedelta(seconds=later)
    return asyncio.run(draft_runner.prepare(account, session_factory=SF, generator=generator, now=lambda: stamp))


def jobs(account):
    async def go(session):
        rows = (await session.execute(select(DraftJob).where(DraftJob.account_id == account))).scalars().all()
        return sorted(rows, key=lambda j: (j.created_at, str(j.id)))

    return run_async(go)


def drafts(account):
    async def go(session):
        rows = (await session.execute(select(MessageDraft).where(MessageDraft.account_id == account))).scalars().all()
        return sorted(rows, key=lambda d: str(d.id))

    return run_async(go)


def signal(lead_id, key, evidence):
    async def go(session):
        source = (
            await session.execute(select(ProspectSource.id).where(ProspectSource.lead_id == uuid.UUID(lead_id)))
        ).scalar_one()
        session.add(
            ProspectSignal(
                account_id=(await session.get(ProspectSource, source)).account_id,
                lead_id=uuid.UUID(lead_id),
                source_id=source,
                signal_key=key,
                state="detected",
                evidence=evidence,
            )
        )

    run_async(go)


def test_without_an_offer_the_prospect_waits_as_offer_required_and_nothing_is_invented():
    account = _account()
    insert_rows(account, [row("Chez Alice", website="https://chez-alice.fr")])
    calls = []
    out = prepare(account, provider(calls))
    (job,) = jobs(account)
    assert out["offer_required"] == 1 and calls == []  # the provider is not even asked
    assert job.status == "offer_required" and job.error_code == "offer_required" and job.draft_id is None
    assert drafts(account) == []


def test_site_present_absent_and_unknown_each_get_their_own_honest_request_and_a_draft_to_review():
    account = _account()
    _offer(account)
    ids = insert_rows(
        account,
        [row("Avec site", website="https://avec-site.fr"), row("Sans site cherché"), row("Etat inconnu")],
    )
    signal(ids[1], "no_website", "The directory entry carries no website")
    calls = []
    out = prepare(account, provider(calls))
    assert out["ready"] == 3 and len(calls) == 3
    by_name = {}
    for job in jobs(account):
        by_name[job.lead_id] = job
    states = {str(job.lead_id): job.site_state for job in by_name.values()}
    assert states == {ids[0]: "site_found", ids[1]: "none_identified", ids[2]: "unknown"}
    prompts = {
        state: next(m[0]["content"] for m in calls if f'"{name}"' in m[1]["content"])
        for state, name in (("none", "Sans site cherché"), ("unknown", "Etat inconnu"), ("found", "Avec site"))
    }
    assert "Je n'ai pas identifié de site officiel pour votre établissement." in prompts["none"]
    assert "Say NOTHING about whether the business has a website" in prompts["unknown"]
    assert "Je n'ai pas identifié" not in prompts["found"] and "Je n'ai pas identifié" not in prompts["unknown"]
    for draft in drafts(account):
        assert draft.status == "draft" and draft.dry_run is True and draft.created_by_user_id is None
        assert (
            draft.template_version == "ai-fr-v1" and "/api/unsubscribe/" in draft.body
        )  # the mandatory footer is there
        assert draft.body.startswith("Bonjour")


def test_a_second_sweep_or_a_refresh_prepares_nothing_twice():
    account = _account()
    _offer(account)
    insert_rows(account, [row("A"), row("B")])
    calls = []
    prepare(account, provider(calls))
    again = prepare(account, provider(calls))
    assert len(calls) == 2 and len(jobs(account)) == 2 and len(drafts(account)) == 2
    assert again["queued"] == 0 and again["ready"] == 0


def test_a_provider_limit_stops_the_sweep_keeps_the_prospects_and_resumes_later_without_duplicates():
    account = _account()
    _offer(account)
    insert_rows(account, [row(f"P{i}") for i in range(4)])
    calls = []
    limit = ai_svc.AIUnavailable("ai_rate_limited", "The AI provider's free limit is reached (HTTP 429).")
    prepare(account, provider(calls, error=limit))
    states = [j.status for j in jobs(account)]
    assert 1 <= states.count("unavailable") <= draft_runner.CONCURRENCY and states.count("queued") >= 2
    assert len(calls) <= draft_runner.CONCURRENCY  # bounded: the free limit is not hammered
    assert drafts(account) == []  # no fake "AI-generated" message
    assert all(j.error_code in (None, "ai_rate_limited") for j in jobs(account))

    async def on_map(session):
        return await prospect_repo.list_positions(session, account)

    assert len(run_async(on_map)) == 4  # the prospects never disappear because their draft is not ready

    # too early: the unavailable ones wait; the queued ones go on
    prepare(account, provider(calls), later=60)
    assert len(drafts(account)) >= 2
    # after the wait, the rest resumes and every prospect has exactly one draft
    prepare(account, provider(calls), later=600)
    assert [j.status for j in jobs(account)] == ["ready"] * 4 and len(drafts(account)) == 4


def test_a_provider_error_is_retried_after_a_wait_with_one_draft_in_the_end():
    account = _account()
    _offer(account)
    insert_rows(account, [row("Solo")])
    calls = []
    prepare(
        account, provider(calls, error=ai_svc.AIUnavailable("ai_failed", "The AI provider did not answer in time."))
    )
    (job,) = jobs(account)
    assert job.status == "failed" and job.attempts == 1 and "did not answer" in job.error
    prepare(account, provider(calls), later=10)
    assert len(calls) == 1 and jobs(account)[0].status == "failed"  # too early: not asked again
    prepare(account, provider(calls), later=200)
    (job,) = jobs(account)
    assert (
        job.status == "ready"
        and job.attempts == 2
        and len(drafts(account)) == 1
        and job.draft_id == drafts(account)[0].id
    )


def test_an_answer_with_an_invented_claim_is_dropped_and_leaves_no_draft():
    account = _account()
    _offer(account)
    insert_rows(account, [row("Resto")])
    bad = {"subject": "Votre site", "body": GOOD["body"] + " Votre page est lente et mal référencée."}
    prepare(account, provider([], answer=bad))
    (job,) = jobs(account)
    assert job.status == "failed" and job.error_code == "draft_rejected" and "safety checks" in job.error
    assert drafts(account) == []


def test_a_hand_edited_draft_is_never_overwritten_and_a_changed_prospect_gets_a_new_proposal_beside_it():
    account = _account()
    _offer(account)
    ids = insert_rows(account, [row("Editée")])
    calls = []
    prepare(account, provider(calls))
    (draft,) = drafts(account)

    async def edit(session):
        stored = await draft_repo.get(session, account, str(draft.id))
        await draft_repo.edit(
            session, stored, subject="Mon objet", body="Mon texte à moi\n\nPied", back_to_review=False
        )

    run_async(edit)
    prepare(account, provider(calls))
    assert len(calls) == 1  # nothing changed: nothing is generated again
    (kept,) = drafts(account)
    assert kept.subject == "Mon objet" and kept.body.startswith("Mon texte à moi") and kept.edited_at is not None

    async def change(session):  # the prospect's data changes: another fingerprint, so another key
        from db.models import Lead

        lead = await session.get(Lead, uuid.UUID(ids[0]))
        lead.city = "Saint-Brieuc"

    run_async(change)
    prepare(account, provider(calls))
    assert len(calls) == 2 and len(drafts(account)) == 2
    assert {d.subject for d in drafts(account)} == {
        "Mon objet",
        "Votre présence en ligne",
    }  # the edited one is untouched


def test_a_slow_provider_never_delays_the_map_or_the_batch():
    account = _account()
    _offer(account)
    insert_rows(account, [row("Lent 1"), row("Lent 2")])

    async def scenario():
        gate = asyncio.Event()

        async def slow(messages):
            await gate.wait()
            return GOOD

        sweep = asyncio.create_task(draft_runner.prepare(account, session_factory=SF, generator=slow))
        await asyncio.sleep(0.6)  # the drafts are generating, held by the provider
        started = time.perf_counter()
        async with SF() as session:
            on_map = await prospect_repo.list_positions(session, account)
            counts = await draft_job_repo.summary(session, account)
        elapsed = time.perf_counter() - started
        gate.set()
        await sweep
        return on_map, counts, elapsed

    on_map, counts, elapsed = asyncio.run(scenario())
    assert len(on_map) == 2 and elapsed < 1.0  # both markers are there while the provider is still thinking
    assert counts["generating"] == 2 and counts["ready"] == 0
    assert [j.status for j in jobs(account)] == ["ready", "ready"]


def test_nothing_is_approved_or_sent_by_the_flow_and_organisations_stay_apart():
    mine, other = _account(), _account()
    _offer(mine)
    insert_rows(mine, [row("Mienne")])
    insert_rows(other, [row("Autre")])  # no offer there
    prepare(mine, provider([]))
    prepare(other, provider([]))
    assert {d.status for d in drafts(mine)} == {"draft"} and drafts(other) == []
    assert [j.status for j in jobs(other)] == ["offer_required"]

    async def sent(session):
        return (await session.execute(select(func.count()).select_from(OutboundMessage))).scalar_one()

    before = run_async(sent)
    prepare(mine, provider([]))
    assert run_async(sent) == before  # the flow has no send path at all


def test_the_endpoints_save_the_offer_and_say_honestly_when_the_ai_is_off():
    uid = uuid.uuid4().hex[:8]
    reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"dj_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "D",
            "organization_name": f"D {uid}",
        },
    )
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    account = uuid.UUID(requests.get(f"{API}/auth/me", headers=h).json()["user"]["org_id"])
    assert requests.get(f"{API}/settings/offer", headers=h).json() == {"configured": False, "offer": None}
    summary = requests.get(f"{API}/prospects/draft-jobs/summary", headers=h).json()
    assert summary["offer_configured"] is False and summary["counts"]["ready"] == 0
    assert requests.put(f"{API}/settings/offer", headers=h, json={**OFFER, "pitch": "court"}).status_code == 422
    insert_rows(account, [row("Via API")])
    saved = requests.put(f"{API}/settings/offer", headers=h, json=OFFER)
    assert saved.status_code == 200 and saved.json()["configured"] is True
    seen = {}
    for _ in range(40):  # the sweep runs in the server's background; the page just reads the state
        seen = requests.get(f"{API}/prospects/draft-jobs/summary", headers=h).json()
        if seen["counts"]["unavailable"] + seen["counts"]["ready"] + seen["counts"]["failed"]:
            break
        time.sleep(0.25)
    assert seen["offer_configured"] is True
    lead_id = str(jobs(account)[0].lead_id)
    job = requests.get(f"{API}/prospects/{lead_id}/draft-job", headers=h).json()
    if not seen["ai_active"]:  # the test server has no AI key: an explicit state, never a fake "AI-generated" message
        assert job["status"] == "unavailable" and job["error_code"] == "ai_not_configured" and job["draft_id"] is None
        assert "AI composer is off" in job["error"]
        assert drafts(account) == []
    run = requests.post(f"{API}/prospects/draft-jobs/run", headers=h)
    assert run.status_code == 202
    assert requests.get(f"{API}/prospects/draft-jobs/summary").status_code in (401, 403)
