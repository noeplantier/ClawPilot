"""A targeted e-mail batch: each lead receives the offer of its case, in the organisation's own words, one recipient per
message, under the same gates as any batch. The preview sends nothing.

Runs against a live server (see .github/workflows/ci.yml); nothing leaves the process (OUTREACH_TEST_SINK).
"""

import os
import uuid

import pytest
import requests
from helpers import open_send_limits, unique_email

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

OFFERS = {
    "language": "fr",
    "default": "refonte_maintenance",
    "offers": {
        "refonte_maintenance": {
            "name": "Refonte de site",
            "pitch": "Un site rapide et à jour, maintenu chaque mois par une équipe locale.",
            "cta": "Un appel de 15 minutes ?",
        },
        "seo_geo": {
            "name": "SEO et GEO",
            "pitch": "Être trouvé sur Google et dans les réponses des assistants IA, mesuré chaque mois.",
            "cta": "Un audit gratuit de 20 minutes ?",
        },
    },
}


@pytest.fixture()
def org():
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"tgt_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Targeted Tester",
            "organization_name": f"Targeted Org {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    open_send_limits(headers)
    return headers


def _lead(h, website=None):
    body = {"full_name": f"Jean {uuid.uuid4().hex[:5]}", "email": unique_email("t"), "company": "Boulangerie Test"}
    resp = requests.post(f"{API}/leads", headers=h, json=body)
    assert resp.status_code == 200, resp.text
    lead_id = resp.json()["id"]
    if website:  # the API keeps a website from the map or a supplied list; written here as those imports write it
        from sqlalchemy import update

        from db.models.lead import Lead
        from tasks._bridge import run_async

        async def go(session):
            await session.execute(update(Lead).where(Lead.id == uuid.UUID(lead_id)).values(website=website))

        run_async(go)
    return lead_id


def test_without_a_complete_offer_a_targeted_batch_is_refused_and_nothing_is_sent(org):
    lead = _lead(org)
    preview = requests.post(f"{API}/messages/email/targeted-preview", headers=org, json={"lead_ids": [lead]}).json()
    assert preview["configured"] is False and preview["counts"] == {"none": 1}
    resp = requests.post(f"{API}/messages/email/batch", headers=org, json={"lead_ids": [lead], "targeted": True})
    assert resp.status_code == 409 and "Offres" in resp.text
    assert requests.get(f"{API}/messages", headers=org).json() == []


def test_each_lead_gets_the_offer_of_its_case_and_an_unknown_site_gets_the_default_never_creation(org):
    assert requests.put(f"{API}/settings/offers", headers=org, json=OFFERS).status_code == 200
    with_site = _lead(org, website="https://boulangerie.example")
    unknown = _lead(org)

    preview = requests.post(
        f"{API}/messages/email/targeted-preview", headers=org, json={"lead_ids": [with_site, unknown]}
    ).json()
    by_lead = {i["lead_id"]: i for i in preview["items"]}
    assert by_lead[with_site] == {"lead_id": with_site, "state": "site_found", "kind": "seo_geo"}
    assert by_lead[unknown] == {"lead_id": unknown, "state": "unknown", "kind": "refonte_maintenance"}
    assert preview["counts"] == {"seo_geo": 1, "refonte_maintenance": 1}
    assert requests.get(f"{API}/messages", headers=org).json() == []  # a preview sends nothing

    resp = requests.post(
        f"{API}/messages/email/batch", headers=org, json={"lead_ids": [with_site, unknown], "targeted": True}
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["dispatched"] == 2
    offers = {r["lead_id"]: r["offer"] for r in out["results"]}
    assert offers == {with_site: "seo_geo", unknown: "refonte_maintenance"}

    sent = requests.get(f"{API}/messages", headers=org).json()
    assert len(sent) == 2 and all(len(m["to"].split(",")) == 1 for m in sent)  # one recipient per message
    subjects = sorted(m["subject"] for m in sent)
    assert subjects == ["Refonte de site · Boulangerie Test", "SEO et GEO · Boulangerie Test"]
    for m in sent:
        assert m["body"].startswith("Bonjour Jean,") and "Origine de vos données" in m["body"]
        assert "pas de site" not in m["body"].lower()  # nothing is said about the lead's web presence


def test_a_plain_batch_still_needs_its_subject_and_body(org):
    lead = _lead(org)
    resp = requests.post(f"{API}/messages/email/batch", headers=org, json={"lead_ids": [lead], "subject": "Hi"})
    assert resp.status_code == 400
