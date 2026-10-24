"""API and worker integration tests against the real CI PostgreSQL, API and Redis services."""

import os
import uuid
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import text

from db.models import Company, JobRun, Lead, PublicPageCache
from tasks._bridge import run_async
from tasks.qualification_tasks import score_selected_leads

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
API = f"{BASE_URL}/api"


def _register():
    uid = uuid.uuid4().hex
    response = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"manual_score_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Manual scoring integration test",
            "organization_name": f"Manual scoring {uid}",
        },
        timeout=10,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return (
        uuid.UUID(body["user"]["org_id"]),
        uuid.UUID(body["user"]["id"]),
        {"Authorization": f"Bearer {body['access_token']}"},
    )


def _seed_lead(account_id, *, enriched):
    lead_id = uuid.uuid4()
    website = f"https://manual-score-{uuid.uuid4().hex}.example"
    company = Company(
        account_id=account_id,
        source_key=f"test:{uuid.uuid4()}",
        name="Persisted scoring test company",
        website=website,
    )

    async def seed(session):
        session.add(company)
        await session.flush()
        session.add(
            Lead(
                id=lead_id,
                account_id=account_id,
                full_name="Persisted scoring test lead",
                company="Persisted scoring test company",
                company_id=company.id,
                website=website,
                vertical="retail",
                city="Paris",
                country="FR",
            )
        )
        if enriched:
            session.add(
                PublicPageCache(
                    url=website,
                    status="completed",
                    data={"emails": [], "phones": [], "socials": [], "technologies": [], "has_form": False},
                    expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                )
            )
        await session.flush()

    run_async(seed)
    return lead_id


def test_manual_scoring_is_authenticated_account_scoped_progressible_and_idempotent():
    account_id, user_id, headers = _register()
    other_account_id, _, other_headers = _register()
    lead_id = _seed_lead(account_id, enriched=True)

    unauthenticated = requests.post(f"{API}/leads/score", json={"lead_ids": [str(lead_id)]}, timeout=10)
    assert unauthenticated.status_code == 401

    queued = requests.post(f"{API}/leads/score", headers=headers, json={"lead_ids": [str(lead_id)]}, timeout=10)
    assert queued.status_code == 202, queued.text
    body = queued.json()
    assert body == {"job_id": body["job_id"], "status": "queued", "lead_count": 1}
    job_id = uuid.UUID(body["job_id"])

    assert requests.get(f"{API}/jobs/{job_id}", headers=other_headers, timeout=10).status_code == 404
    assert (
        requests.post(
            f"{API}/leads/score", headers=other_headers, json={"lead_ids": [str(lead_id)]}, timeout=10
        ).status_code
        == 404
    )

    result = score_selected_leads(str(job_id), str(account_id), [str(lead_id)])
    assert result == {"processed": 1, "failed": 0}
    status = requests.get(f"{API}/jobs/{job_id}", headers=headers, timeout=10)
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "succeeded"
    assert status.json()["processed_items"] == 1
    assert status.json()["created_by"] == str(user_id)

    async def load(session):
        lead = await session.get(Lead, lead_id)
        job = await session.get(JobRun, job_id)
        return lead, job

    lead, job = run_async(load)
    before = (lead.website_quality, lead.digital_maturity, lead.fit_score, lead.priority, lead.qualification_scored_at)
    assert 0 <= lead.fit_score <= 100
    assert job.account_id == account_id

    # Duplicate delivery of the same completed task is a no-op.
    assert score_selected_leads(str(job_id), str(account_id), [str(lead_id)]) == result
    lead, _ = run_async(load)
    after = (lead.website_quality, lead.digital_maturity, lead.fit_score, lead.priority, lead.qualification_scored_at)
    assert after == before


def test_manual_scoring_rejects_empty_or_oversized_selections_and_tracks_unenriched_leads():
    account_id, _, headers = _register()
    lead_id = _seed_lead(account_id, enriched=False)
    assert requests.post(f"{API}/leads/score", headers=headers, json={"lead_ids": []}, timeout=10).status_code == 422
    too_many = [str(uuid.uuid4()) for _ in range(201)]
    assert (
        requests.post(f"{API}/leads/score", headers=headers, json={"lead_ids": too_many}, timeout=10).status_code == 422
    )

    queued = requests.post(f"{API}/leads/score", headers=headers, json={"lead_ids": [str(lead_id)]}, timeout=10)
    assert queued.status_code == 202, queued.text
    job_id = queued.json()["job_id"]
    assert score_selected_leads(job_id, str(account_id), [str(lead_id)]) == {"processed": 0, "failed": 1}
    status = requests.get(f"{API}/jobs/{job_id}", headers=headers, timeout=10).json()
    assert status["status"] == "failed"
    assert "completed enrichment" in status["error"]

    lead_response = requests.get(f"{API}/leads", headers=headers, timeout=10)
    assert lead_response.status_code == 200, lead_response.text
    item = next(row for row in lead_response.json() if row["id"] == str(lead_id))
    assert item["enrichment_status"] == "required"
    assert item["fit_score"] is None


def test_manual_scoring_migration_enables_rls_without_public_table_grants():
    async def check(session):
        rls = await session.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.job_runs'::regclass"))
        return rls.scalar_one()

    assert run_async(check) is True
