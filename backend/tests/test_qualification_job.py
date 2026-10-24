"""The Celery qualification job scores persisted enrichment and is safe to rerun."""

import os
import uuid
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import select

from db.models import Company, Lead, PublicPageCache
from tasks._bridge import run_async
from tasks.qualification_tasks import score_enriched_leads

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _register():
    uid = uuid.uuid4().hex[:10]
    response = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"qualification_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Qualification test",
            "organization_name": f"Qualification {uid}",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["org_id"]), {"Authorization": f"Bearer {body['access_token']}"}


def test_celery_job_scores_completed_cache_once_and_leaves_unenriched_leads_unknown():
    account_id, headers = _register()
    lead_id = uuid.uuid4()
    unenriched_id = uuid.uuid4()
    website = f"https://qualification-{uuid.uuid4().hex[:12]}.example"

    async def seed(session):
        company = Company(
            account_id=account_id,
            source_key=f"test:{uuid.uuid4()}",
            name="Persisted company",
            website=website,
        )
        session.add(company)
        await session.flush()
        session.add_all(
            [
                Lead(
                    id=lead_id,
                    account_id=account_id,
                    full_name="Persisted company",
                    company="Persisted company",
                    company_id=company.id,
                    vertical="retail",
                    city="Paris",
                    country="FR",
                    title="Owner",
                ),
                Lead(id=unenriched_id, account_id=account_id, full_name="Not enriched"),
                PublicPageCache(
                    url=website,
                    status="completed",
                    data={
                        "emails": ["hello@qualification.example"],
                        "phones": [],
                        "socials": ["https://linkedin.com/company/qualification"],
                        "technologies": ["wordpress"],
                        "has_form": True,
                    },
                    expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                ),
            ]
        )

    run_async(seed)
    assert score_enriched_leads() == 1
    assert score_enriched_leads() == 0

    async def load_scores(session):
        rows = await session.execute(select(Lead).where(Lead.id.in_([lead_id, unenriched_id])))
        return {lead.id: lead for lead in rows.scalars()}

    leads = run_async(load_scores)
    scored = leads[lead_id]
    assert 0 <= scored.website_quality <= 100
    assert 0 <= scored.digital_maturity <= 100
    assert 0 <= scored.fit_score <= 100
    assert scored.priority in {"low", "medium", "high"}
    assert scored.qualification_scored_at is not None
    assert leads[unenriched_id].fit_score is None

    response = requests.get(f"{API}/leads", headers=headers)
    assert response.status_code == 200, response.text
    api_lead = next(item for item in response.json() if item["id"] == str(lead_id))
    assert api_lead["fit_score"] == scored.fit_score
    assert api_lead["priority"] == scored.priority
