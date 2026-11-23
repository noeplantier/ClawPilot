"""The CRM list answers in a fixed number of queries, whatever the number of leads, with the same fields as before.

`GET /leads` used to resolve each lead's source, primary contact, both consents and latest prospect score one lead at a
time: up to five queries per lead, 54 s for 80 leads in production. The list now batches them (`lead_repo.load_extras`).
The leads are created over HTTP; the queries are counted in-process on the same database. Nothing is sent.
"""

import os
import uuid

import requests
from helpers import unique_email
from sqlalchemy import event

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _org():
    uid = uuid.uuid4().hex[:10]
    reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"lq_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "List Queries",
            "organization_name": f"LQ {uid}",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    me = requests.get(f"{API}/auth/me", headers=headers).json()["user"]
    return headers, uuid.UUID(me["org_id"])


def _leads(headers, n, **extra):
    ids = []
    for i in range(n):
        body = {"full_name": f"Lead {i}", "email": unique_email("lq"), "source": "Salon 2025", **extra}
        resp = requests.post(f"{API}/leads", headers=headers, json=body)
        assert resp.status_code == 200, resp.text
        ids.append(resp.json()["id"])
    return ids


def _count_queries(account_id):
    """(number of SQL statements, rows) of one `lead_repo.list_leads` call for this organisation."""
    from repositories import lead_repo
    from tasks import _bridge

    seen = []

    def count(*_args, **_kwargs):
        seen.append(1)

    async def go(session):
        event.listen(_bridge._engine.sync_engine, "before_cursor_execute", count)
        try:
            return await lead_repo.list_leads(session, account_id)
        finally:
            event.remove(_bridge._engine.sync_engine, "before_cursor_execute", count)

    rows = _bridge.run_async(go)
    return len(seen), rows


def test_the_list_costs_the_same_number_of_queries_for_three_leads_or_fifteen():
    few_headers, few_org = _org()
    _leads(few_headers, 3)
    many_headers, many_org = _org()
    _leads(many_headers, 15, email_opt_in=True, consent_source="signed form")

    few_queries, few_rows = _count_queries(few_org)
    many_queries, many_rows = _count_queries(many_org)
    assert (len(few_rows), len(many_rows)) == (3, 15)
    assert many_queries == few_queries, (few_queries, many_queries)  # no query per lead any more
    assert many_queries <= 8


def test_batched_fields_match_the_one_lead_lookups_and_stay_in_their_organisation():
    from repositories import consent_repo
    from tasks import _bridge

    headers, org = _org()
    ids = _leads(headers, 2, email_opt_in=True, consent_source="signed form") + _leads(headers, 1)
    other_headers, _ = _org()
    other_ids = _leads(other_headers, 2)

    _, rows = _count_queries(org)
    assert {str(lead.id) for lead, _ in rows} == set(ids)  # another organisation's leads are never listed
    assert not {str(lead.id) for lead, _ in rows} & set(other_ids)

    async def one_by_one(session):
        out = {}
        for lead, extra in rows:
            contact_id = await consent_repo.get_primary_contact_id(session, lead.id)
            out[lead.id] = (
                contact_id,
                await consent_repo.get_status(session, contact_id, "email") if contact_id else "unknown",
                await consent_repo.get_status(session, contact_id, "whatsapp") if contact_id else "unknown",
            )
        return out

    expected = _bridge.run_async(one_by_one)
    for lead, extra in rows:
        assert (extra.contact_id, extra.email_consent, extra.whatsapp_consent) == expected[lead.id]
        assert extra.source == "Salon 2025" and extra.prospect_score is None  # a CRM lead has no prospect score
    assert sum(1 for _, extra in rows if extra.email_consent == "opted_in") == 2

    listed = requests.get(f"{API}/leads", headers=headers)
    assert listed.status_code == 200 and {lead["id"] for lead in listed.json()} == set(ids)
    assert all(lead["source"] == "Salon 2025" for lead in listed.json())
