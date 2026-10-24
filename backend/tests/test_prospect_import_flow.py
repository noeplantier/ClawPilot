"""Prospect list import end to end. The server stays with the import flag OFF (the safe default), so the flag-on
paths run in this process on the same database, like tests/test_outbound_live.py. No network, nothing is sent."""

import os
import uuid

import pytest
import requests

if not os.environ.get("DATABASE_URL"):
    pytest.skip("needs DATABASE_URL (same database as the server)", allow_module_level=True)

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from db.models import AuditLog  # noqa: E402
from models import ImportIn  # noqa: E402
from routes import prospect_imports as routes  # noqa: E402
from tasks._bridge import run_async  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
UID = uuid.uuid4().hex[:6]

CSV = (
    "Nom,Email,Telephone,Site,Ville\n"
    "Atelier Dupont,contact@atelier-dupont-{u}.example,01 23 45 67 89,https://atelier-dupont-{u}.example,Lyon\n"
    "Atelier Dupont SARL,contact@atelier-dupont-{u}.example,,,Lyon\n"
    "Boulangerie Martin,martin@boulangerie-martin-{u}.example,,,Tours\n"
    "Cabinet Durand,durand@cabinet-durand-{u}.example,,,Paris\n"
    "Mauvais Email,pas-un-email,,,Nice\n"
    ",orphan@x.example,,,\n"
)


@pytest.fixture()
def org(monkeypatch):
    monkeypatch.setenv("FEATURE_PROSPECT_IMPORT", "true")
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"imp_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Import Tester",
            "organization_name": f"Import Org {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = requests.get(f"{API}/auth/me", headers=headers).json()["user"]
    return {"headers": headers, "user": me}


def _payload(**kw):
    base = dict(
        format="csv",
        content=CSV.format(u=UID),
        filename="clients.csv",
        origin="Customer list exported from our own CRM",
        legal_basis="legitimate_interest_b2b",
    )
    return ImportIn(**{**base, **kw})


def _call(org, payload):
    async def go(session):
        return await routes.import_prospects(payload, user={**org["user"]}, session=session)

    return run_async(go)


def _prospects(org):
    return requests.get(f"{API}/prospects", headers=org["headers"], params={"limit": 200}).json()["items"]


def test_the_import_is_closed_while_the_flag_is_off(monkeypatch):
    monkeypatch.delenv("FEATURE_PROSPECT_IMPORT", raising=False)
    uid = uuid.uuid4().hex[:10]
    token = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"off_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "O",
            "organization_name": uid,
        },
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    body = {"format": "csv", "content": "name\nA", "origin": "my own customer list", "legal_basis": "consent"}
    refused = requests.post(f"{API}/prospect-imports", headers=h, json=body)
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "feature_disabled"
    assert requests.post(f"{API}/prospect-imports", json=body).status_code == 401
    assert requests.get(f"{API}/prospect-imports", headers=h).json() == []  # reading the history is always allowed


def test_validation_rejects_a_vague_origin_and_an_unknown_legal_basis():
    with pytest.raises(ValueError):
        _payload(origin="list")
    with pytest.raises(ValueError):
        _payload(legal_basis="because")


def test_preview_reports_everything_and_writes_nothing(org):
    out = _call(org, _payload())
    assert out.preview is True and out.batch_id is None
    assert (out.rows_total, out.rows_valid, out.errors_count) == (6, 4, 2)
    assert {e.row for e in out.errors} == {5, 6}
    assert (out.entities, out.duplicates_merged, out.created, out.updated, out.suppressed) == (3, 1, 3, 0, 0)
    assert _prospects(org) == []
    assert requests.get(f"{API}/prospect-imports", headers=org["headers"]).json() == []


def test_committing_needs_the_attestation(org):
    with pytest.raises(HTTPException) as refused:
        _call(org, _payload(preview=False))
    assert refused.value.status_code == 422 and refused.value.detail["code"] == "attestation_required"
    assert _prospects(org) == []


def test_commit_creates_pending_prospects_with_provenance_and_honest_signals(org):
    out = _call(org, _payload(preview=False, attestation=True, vertical="artisans", country="FR"))
    assert out.preview is False and out.created == 3 and out.batch_id

    items = _prospects(org)
    assert sorted(p["name"] for p in items) == ["Atelier Dupont", "Boulangerie Martin", "Cabinet Durand"]
    assert {p["review_status"] for p in items} == {"pending"}  # a human still has to approve every one
    assert {p["vertical"] for p in items} == {"artisans"}

    martin = next(p for p in items if p["name"] == "Boulangerie Martin")
    detail = requests.get(f"{API}/prospects/{martin['id']}", headers=org["headers"]).json()
    source = detail["sources"][0]
    assert source["source_name"].startswith("import:")
    assert (
        "Customer list exported from our own CRM" in source["license_note"]
        and "legitimate_interest_b2b" in source["license_note"]
    )
    states = {s["key"]: s["state"] for s in detail["signals"]}
    assert states["no_website"] == "unknown"  # an empty cell is not evidence that there is no website
    assert states["website_unreachable"] == "unknown" and states["not_mobile_friendly"] == "unknown"
    assert not any(
        s["state"] == "detected" and s["key"] in ("no_website", "incomplete_listing") for s in detail["signals"]
    )

    batches = requests.get(f"{API}/prospect-imports", headers=org["headers"]).json()
    assert len(batches) == 1
    batch = batches[0]
    assert (
        batch["origin"] == "Customer list exported from our own CRM"
        and batch["legal_basis"] == "legitimate_interest_b2b"
    )
    assert batch["rows_total"] == 6 and batch["filename"] == "clients.csv" and batch["summary"]["errors_count"] == 2


def test_reimporting_the_same_file_is_flagged_and_creates_no_duplicate(org):
    _call(org, _payload(preview=False, attestation=True))
    preview = _call(org, _payload())
    assert preview.already_imported is True and preview.created == 0 and preview.updated == 3
    again = _call(org, _payload(preview=False, attestation=True))
    assert again.created == 0 and again.updated == 3
    assert len(_prospects(org)) == 3


def test_a_suppressed_address_is_never_imported(org):
    h = org["headers"]
    sup = requests.post(
        f"{API}/prospects/suppressions", headers=h, json={"email": f"martin@boulangerie-martin-{UID}.example"}
    )
    assert sup.status_code == 200
    preview = _call(org, _payload())
    assert preview.suppressed == 1 and preview.created == 2
    out = _call(org, _payload(preview=False, attestation=True))
    assert out.suppressed == 1 and out.created == 2
    assert "Boulangerie Martin" not in [p["name"] for p in _prospects(org)]


def test_an_unusable_file_and_an_empty_result_are_refused(org):
    with pytest.raises(HTTPException) as bad:
        _call(org, _payload(content="email\na@a.example"))
    assert bad.value.status_code == 422 and bad.value.detail["code"] == "import_rejected"
    with pytest.raises(HTTPException) as empty:
        _call(org, _payload(content="name,email\nA,nope\n", preview=False, attestation=True))
    assert empty.value.detail["code"] == "nothing_to_import"


def test_the_audit_trail_has_hashes_and_counts_never_the_rows(org):
    out = _call(org, _payload(preview=False, attestation=True))

    async def entries(session):
        rows = await session.execute(
            select(AuditLog).where(
                AuditLog.account_id == uuid.UUID(org["user"]["org_id"]), AuditLog.action == "prospect_import.committed"
            )
        )
        return [r.diff for r in rows.scalars()]

    (diff,) = run_async(entries)
    assert set(diff) == {
        "sha256",
        "legal_basis",
        "rows_total",
        "created",
        "suppressed",
        "check_websites",
        "sites_checked",
    }
    assert len(diff["sha256"]) == 64 and diff["created"] == 3 and out.batch_id
    assert "atelier-dupont" not in str(diff)  # the list content itself is never written to the audit log


def _commit(**kw):
    return _payload(preview=False, attestation=True, **kw)


def test_checking_websites_is_refused_while_external_sources_are_off(org, monkeypatch):
    monkeypatch.delenv("FEATURE_EXTERNAL_SOURCES", raising=False)
    with pytest.raises(HTTPException) as refused:
        _call(org, _commit(check_websites=True))
    assert refused.value.status_code == 409 and refused.value.detail["code"] == "external_sources_disabled"
    assert _prospects(org) == []  # refused before anything was written


def test_with_the_flag_on_only_listed_sites_are_fetched_and_the_rest_stays_unknown(org, monkeypatch):
    """The fetcher is replaced: no network. It proves the wiring (flag + option → fetcher → signals → summary)."""
    from services.outreach_os.types import SiteSnapshot

    asked: list[str] = []

    class FakeFetcher:
        def fetch(self, url):
            asked.append(url)
            return SiteSnapshot(url=url, status=200, html="<html><body>Bienvenue</body></html>")

    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")
    monkeypatch.setattr(routes, "HttpSiteFetcher", FakeFetcher)
    out = _call(org, _commit(check_websites=True))
    assert out.sites_checked == 1 and asked == [f"https://atelier-dupont-{UID}.example"]  # the only row with a site
    dupont = next(p for p in _prospects(org) if p["name"].startswith("Atelier Dupont"))
    detail = requests.get(f"{API}/prospects/{dupont['id']}", headers=org["headers"]).json()
    states = {s["key"]: s["state"] for s in detail["signals"]}
    assert states["website_unreachable"] == "not_detected"  # it answered
    other = next(p for p in _prospects(org) if p["name"] == "Cabinet Durand")
    other_states = {
        s["key"]: s["state"]
        for s in requests.get(f"{API}/prospects/{other['id']}", headers=org["headers"]).json()["signals"]
    }
    assert other_states["website_unreachable"] == "unknown"  # no site listed: nothing concluded


def test_without_the_option_nothing_is_fetched_even_with_the_flag_on(org, monkeypatch):
    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")

    class Boom:
        def __init__(self):
            raise AssertionError("the fetcher must not be built without check_websites")

    monkeypatch.setattr(routes, "HttpSiteFetcher", Boom)
    assert _call(org, _commit()).sites_checked == 0


def test_a_missing_email_is_filled_only_from_a_mailto_on_the_businesss_own_site(org, monkeypatch):
    from services.outreach_os.types import SiteSnapshot

    class SiteWithMailto:
        def fetch(self, url):
            return SiteSnapshot(
                url=url, status=200, html='<a href="mailto:bonjour@atelier-dupont-%s.example">Mail</a>' % UID
            )

    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")
    monkeypatch.setattr(routes, "HttpSiteFetcher", SiteWithMailto)
    csv = f"Nom,Site,Ville\nAtelier Dupont,https://atelier-dupont-{UID}.example,Lyon\nSans Site,,Paris\n"
    out = _call(org, _commit(content=csv, check_websites=True))
    assert out.sites_checked == 1
    items = {p["name"]: p for p in _prospects(org)}
    detail = requests.get(f"{API}/prospects/{items['Atelier Dupont']['id']}", headers=org["headers"]).json()
    assert detail["contact_email"] == f"bonjour@atelier-dupont-{UID}.example"
    history = requests.get(f"{API}/prospects/{items['Atelier Dupont']['id']}/events", headers=org["headers"]).json()
    assert "prospect.email_found" in [e["action"] for e in history]  # provenance is in the audit trail
    other = requests.get(f"{API}/prospects/{items['Sans Site']['id']}", headers=org["headers"]).json()
    assert other["contact_email"] is None  # nothing guessed for a business without a site
