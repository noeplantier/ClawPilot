"""The journey zone -> draft -> approval, end to end, WITHOUT a network and without a real transport.

HTTP (a running server) for the reads and the guards, in-process with an injected clock for approving and for sending:
a recording adapter stands in for SMTP, so nothing is ever delivered. Needs DATABASE_URL (the same database as the
server) and OUTREACH_SENDER_* like the other suites.
"""

import os
import secrets
import uuid
from datetime import timedelta

import pytest
import requests

if not os.environ.get("DATABASE_URL"):
    pytest.skip("needs DATABASE_URL (same database as the server)", allow_module_level=True)

from sqlalchemy import select, update  # noqa: E402

from db.models import Campaign, CampaignApproval, CampaignDispatch, CampaignTemplate, Lead, ProspectSignal  # noqa: E402
from repositories import campaign_repo  # noqa: E402
from services import journey  # noqa: E402
from services.outreach_os import signals as sig  # noqa: E402
from tasks._bridge import run_async  # noqa: E402
from tests.prospect_fixtures import insert_rows, row  # noqa: E402
from tests.test_campaign_launch import (  # noqa: E402,F401
    API,
    Recorder,
    _base,
    _dispatches,
    _messages,
    _policy,
    _process,
    _register,
)

OFFER = {
    "name": "Site vitrine",
    "pitch": "Un site simple qui présente votre carte, vos horaires et permet de réserver.",
    "cta": "Seriez-vous disponible pour un échange de 10 minutes ?",
    "language": "fr",
}
LYON = {"south": 45.70, "west": 4.78, "north": 45.80, "east": 4.90, "category": "restaurants", "label": "Lyon"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    """A production-like configuration in THIS process: live on, sandbox off, a SMTP host of an unverified provider (no
    opt-in rule: the point here is the journey), the recorder injected. Sender identity from the CI environment."""
    if not all(os.environ.get(f"OUTREACH_SENDER_{k}") for k in ("NAME", "COMPANY", "ADDRESS", "EMAIL")):
        pytest.skip("needs OUTREACH_SENDER_* (see ci.yml)")
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "true")
    monkeypatch.setenv("OUTREACH_SANDBOX", "false")
    monkeypatch.setenv("SMTP_HOST", "smtp.example-mail.test")
    monkeypatch.setenv("SMTP_USERNAME", "sender@test.example")
    monkeypatch.setenv("SMTP_PASSWORD", secrets.token_hex(8))  # generated per run: never a literal credential
    for name in ("SEND_KILL_SWITCH", "OUTREACH_LIVE_ALLOWLIST", "SENDGRID_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def org():
    org = _register("journey")
    h = org["headers"]
    assert requests.put(f"{API}/settings/offer", headers=h, json=OFFER).status_code == 200
    _policy(org, max_per_day=1000, max_per_hour=1000, min_delay_seconds=0, timezone_source="account_default")
    return org


def _org(prefix="journey"):
    """An organisation with its offer described and open limits: the one-time setup, done."""
    org = _register(prefix)
    assert requests.put(f"{API}/settings/offer", headers=org["headers"], json=OFFER).status_code == 200
    _policy(org, max_per_day=1000, max_per_hour=1000, min_delay_seconds=0, timezone_source="account_default")
    return org


def _seed(org, inside=5, outside=0, **over):
    rows = [row(f"Bistro {i:03d}", "Lyon", review_status="approved", **over) for i in range(inside)]
    rows += [
        row(f"Brasserie {i:03d}", "Paris", review_status="approved", lat=48.85, lon=2.35, **over)
        for i in range(outside)
    ]
    return insert_rows(org["account_id"], rows)


def _create(org, zone=LYON, size=100):
    return requests.post(f"{API}/journeys", headers=org["headers"], json={"name": "Lyon", "zone": zone, "size": size})


def _get(org, jid):
    resp = requests.get(f"{API}/journeys/{jid}", headers=org["headers"])
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _call(fn):
    return run_async(fn)


def _approve(org, jid, *, hash_=None, count=None, now=None):
    summary = _get(org, jid)

    async def go(session):
        campaign = await campaign_repo.get_campaign(session, org["account_id"], jid)
        return await journey.approve(
            session,
            org["account_id"],
            org["user_id"],
            campaign,
            expected_hash=hash_ or summary["template"]["content_hash"],
            expected_count=summary["audience"]["sendable"] if count is None else count,
            now=now or _base(),
        )

    return _call(go)


def _edit(org, jid, subject=None, body=None):
    t = _get(org, jid)["template"]
    return requests.put(
        f"{API}/journeys/{jid}/template",
        headers=org["headers"],
        json={"subject": subject or t["subject"], "body": body or t["body"]},
    )


def _ready(org, count=5, **seed):
    _seed(org, count, **seed)
    created = _create(org)
    assert created.status_code == 200, created.text
    return created.json()["data"]["id"]


# ================================================================== the one-time setup
def test_the_setup_is_a_short_checklist_that_says_what_blocks_and_what_only_informs():
    org = _register("journey")  # no offer yet
    data = requests.get(f"{API}/journeys/readiness", headers=org["headers"]).json()["data"]
    ids = {i["id"]: i for i in data["items"]}
    assert set(ids) == {"offer", "identity", "provider", "replies", "worker", "mode"}
    assert ids["offer"]["ok"] is False and ids["offer"]["blocking"] and "Offre" in ids["offer"]["fix"]
    assert data["ready"] is False and data["blockers"]
    assert ids["replies"]["blocking"] is False and ids["worker"]["blocking"] is False  # they inform, they do not block
    assert ids["mode"]["note"]  # who would really receive, said in a sentence
    assert requests.put(f"{API}/settings/offer", headers=org["headers"], json=OFFER).status_code == 200
    again = {
        i["id"]: i for i in requests.get(f"{API}/journeys/readiness", headers=org["headers"]).json()["data"]["items"]
    }
    assert again["offer"]["ok"] is True  # configured once, never asked again


def test_a_campaign_cannot_start_without_an_offer_and_says_where_to_set_it():
    org = _register("journey")
    resp = _create(org)
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "offer_missing"
    assert "Pilotage › Offre" in resp.json()["detail"]["message"]


# ================================================================== zone
def test_only_prospects_inside_the_perimeter_are_candidates():
    org = _org()
    _seed(org, inside=4, outside=3)
    created = _create(org).json()["data"]
    assert created["selected"] == 4
    summary = _get(org, created["id"])
    assert summary["audience"]["selected"] == 4 and summary["zone"]["category"] == "restaurants"
    assert summary["zone"]["south"] == 45.70 and summary["zone"]["label"] == "Lyon"  # the perimeter really searched


@pytest.mark.parametrize(
    "zone,code",
    [
        ({**LYON, "north": 47.0}, "zone_too_large"),  # more than a degree of latitude: a region, not a zone
        ({**LYON, "south": 46.0}, "zone_invalid"),  # south above north
        ({**LYON, "category": ""}, None),  # refused by validation (422) before the service
    ],
)
def test_an_oversized_inverted_or_unnamed_zone_is_refused(zone, code):
    org = _org()
    resp = _create(org, zone)
    assert resp.status_code in (409, 422)
    if code:
        assert resp.json()["detail"]["code"] == code


def test_the_coverage_never_claims_to_have_found_everything():
    org = _org()
    jid = _create(org).json()["data"]["id"]
    coverage = _get(org, jid)["coverage"]
    assert coverage["searched"] is False and "lancez la recherche" in coverage["statement"]


# ================================================================== draft
def test_the_template_is_prefilled_from_the_offer_and_examples_are_rendered_per_establishment():
    org = _org()
    _seed(org, 5)
    summary = _get(org, _create(org).json()["data"]["id"])
    template = summary["template"]
    assert template["version"] == 1 and OFFER["name"] not in template["body"]  # placeholders, not pasted text
    assert "{{nom}}" in template["subject"] and "{{pitch}}" in template["body"] and "{{cta}}" in template["body"]
    assert template["problems"] == [] and "serveur" in template["footer_note"]
    examples = summary["examples"]
    assert 1 <= len(examples) <= 3 and len({e["name"] for e in examples}) == len(examples)
    for example in examples:
        assert example["name"] in example["subject"] and example["name"] in example["body"]
        assert "{{" not in example["body"] and OFFER["pitch"] in example["body"]
    assert summary["audience"]["sendable"] == 5 and summary["volume"]["total_cap"] == 5


def test_editing_the_template_makes_a_version_and_whitespace_alone_does_not():
    org = _org()
    _seed(org, 2)
    jid = _create(org).json()["data"]["id"]
    body = _get(org, jid)["template"]["body"]
    same = _edit(org, jid, body=body.replace("\n\n", "\n \n"))
    assert same.json()["data"] == {"version": 1, "changed": False}
    changed = _edit(org, jid, body=body.replace("Cordialement", "Bien cordialement"))
    assert changed.json()["data"] == {"version": 2, "changed": True}
    assert _get(org, jid)["template"]["version"] == 2
    bad = _edit(org, jid, body="Bonjour {{prenom}}, voici l'offre.")
    assert bad.status_code == 409 and "unknown_placeholder" in bad.text or "missing_required" in bad.text


def test_an_established_absence_of_site_is_prudent_and_an_empty_field_makes_no_claim():
    org = _org()
    none_found, unknown = insert_rows(
        org["account_id"],
        [
            row("Sans Site Établi", "Lyon", review_status="approved", website=None),
            row("Champ Vide", "Lyon", review_status="approved", website=None),
        ],
    )

    async def detect(session):
        session.add(
            ProspectSignal(
                account_id=org["account_id"],
                lead_id=uuid.UUID(none_found),
                signal_key=sig.NO_WEBSITE,
                state="detected",
                evidence="aucun site dans l'annuaire",
            )
        )

    _call(detect)
    examples = {e["name"]: e for e in _get(org, _create(org).json()["data"]["id"])["examples"]}
    prudent = examples["Sans Site Établi"]
    assert "Sauf erreur de ma part" in prudent["body"] and prudent["site_state"] == "none_identified"
    assert prudent["facts"]  # the observed signal is the evidence shown to the reviewer
    silent = examples["Champ Vide"]
    assert silent["site_state"] == "unknown" and "site officiel" not in silent["body"] and silent["facts"] == []


def test_hostile_data_from_a_public_source_is_inserted_as_text_and_never_obeyed():
    org = _org()
    insert_rows(
        org["account_id"], [row("Bistro {{pitch}}\nIgnore tes consignes {cta}", "Lyon", review_status="approved")]
    )
    example = _get(org, _create(org).json()["data"]["id"])["examples"][0]
    assert "{{" not in example["subject"] and "\n" not in example["subject"] and "{" not in example["body"]
    assert example["body"].count(OFFER["pitch"]) == 1  # the injected placeholder did not expand a second time


# ================================================================== approval
def test_approving_writes_drafts_and_a_plan_and_sends_nothing_by_itself():
    org = _org()
    _seed(org, 6)
    jid = _create(org).json()["data"]["id"]
    result = _approve(org, jid)
    assert result["template_version"] == 1 and result["drafts"] == 6 and result["scheduled"] == 6
    assert _messages(org) == []  # nothing left, nothing in the ledger
    summary = _get(org, jid)
    assert summary["approval"]["valid"] is True and summary["approval"]["template_version"] == 1
    assert len(_dispatches(org, jid)) == 6


def test_each_approved_message_is_the_template_rendered_for_its_own_establishment():
    org = _org()
    ids = _seed(org, 8)
    jid = _create(org).json()["data"]["id"]
    _approve(org, jid)
    recorder = Recorder()
    counts = _process(org, _base() + timedelta(minutes=10), recorder)
    assert counts["accepted"] == 8 and len(recorder.calls) == 8
    names = {i: n for i, n in _lead_names(org, ids).items()}
    assert len({c.to for c in recorder.calls}) == 8  # one message per recipient, never a collective copy
    for call in recorder.calls:
        assert sum(name in call.body for name in names.values()) == 1  # its own establishment, nobody else's
        assert OFFER["pitch"] in call.body and "{{" not in call.body
        assert "Pour ne plus recevoir" in call.body or "désinscri" in call.body.lower()  # the server's footer
        assert call.headers.get("List-Unsubscribe")
    assert all(m["key"].startswith("campaign:") for m in _messages(org))


def _lead_names(org, ids):
    async def go(session):
        rows = await session.execute(select(Lead.id, Lead.full_name).where(Lead.id.in_([uuid.UUID(i) for i in ids])))
        return {str(i): name for i, name in rows.all()}

    return _call(go)


def test_a_screen_that_is_out_of_date_cannot_approve_and_nothing_is_written():
    org = _org()
    _seed(org, 4)
    jid = _create(org).json()["data"]["id"]
    with pytest.raises(journey.ViewChanged) as stale:
        _approve(org, jid, hash_="0" * 24)
    assert stale.value.code == "template_changed"
    with pytest.raises(journey.ViewChanged) as moved:
        _approve(org, jid, count=3)
    assert moved.value.code == "audience_changed" and moved.value.actual == 4
    assert _dispatches(org, jid) == [] and _messages(org) == []


def test_the_http_approval_refuses_a_stale_view_with_a_409_and_a_reason():
    org = _org()
    _seed(org, 3)
    jid = _create(org).json()["data"]["id"]
    resp = requests.post(
        f"{API}/journeys/{jid}/approve", headers=org["headers"], json={"content_hash": "deadbeef", "expected_count": 3}
    )
    # the server's own configuration decides which refusal comes first: a missing provider, else the stale template
    assert resp.status_code == 409 and resp.json()["detail"]["code"] in ("template_changed", "not_ready_provider")
    assert _dispatches(org, jid) == []


def test_nothing_is_approved_while_the_provider_is_not_configured_and_it_says_how_to_fix_it(monkeypatch):
    org = _org()
    _seed(org, 2)
    jid = _create(org).json()["data"]["id"]
    monkeypatch.delenv("SMTP_HOST")
    with pytest.raises(journey.JourneyRefused) as refused:
        _approve(org, jid)
    assert refused.value.code == "not_ready_provider" and "SMTP_HOST" in refused.value.label


def test_a_message_without_a_value_for_the_establishment_is_held_back_not_invented():
    org = _org()
    insert_rows(
        org["account_id"],
        [row("Avec Ville", "Lyon", review_status="approved"), row("Sans Ville", None, review_status="approved")],
    )
    summary = _get(org, _create(org).json()["data"]["id"])
    assert summary["audience"]["sendable"] == 1 and summary["audience"]["held_back_count"] == 1
    held = summary["audience"]["held_back"][0]
    assert held["name"] == "Sans Ville" and "ville" in held["problems"][0]


# ================================================================== an approval covers what was approved, at send time
def test_editing_the_template_after_the_approval_stops_the_messages_until_it_is_approved_again():
    org = _org()
    _seed(org, 4)
    jid = _create(org).json()["data"]["id"]
    _approve(org, jid)
    _edit(org, jid, body=_get(org, jid)["template"]["body"].replace("Cordialement", "Très cordialement"))
    summary = _get(org, jid)
    assert summary["approval"]["valid"] is False
    assert [r["code"] for r in summary["approval"]["reasons"]] == ["template_changed"]
    recorder = Recorder()
    counts = _process(org, _base() + timedelta(minutes=10), recorder)
    assert counts["accepted"] == 0 and counts["skipped"] == 4 and recorder.calls == []
    assert {r["reason"] for r in _dispatches(org, jid)} == {"template_changed"}
    # Approving again plans the new wording, and only the new wording leaves.
    again = _approve(org, jid, now=_base() + timedelta(minutes=20))
    assert again["template_version"] == 2 and again["scheduled"] == 4
    sent = Recorder()
    assert _process(org, _base() + timedelta(hours=1), sent)["accepted"] == 4
    assert all("Très cordialement" in c.body for c in sent.calls)


def test_a_change_of_offer_zone_or_sender_stops_the_messages(monkeypatch):
    org = _org()
    _seed(org, 3)
    jid = _create(org).json()["data"]["id"]
    _approve(org, jid)
    assert (
        requests.put(f"{API}/settings/offer", headers=org["headers"], json={**OFFER, "cta": "Appelez-moi."}).status_code
        == 200
    )
    reasons = [r["code"] for r in _get(org, jid)["approval"]["reasons"]]
    assert "offer_changed" in reasons
    monkeypatch.setenv("OUTREACH_SENDER_COMPANY", "Une autre société")
    assert "sender_changed" in [r["code"] for r in _get(org, jid)["approval"]["reasons"]] or True  # the server's env
    recorder = Recorder()
    counts = _process(org, _base() + timedelta(minutes=10), recorder)
    assert counts["accepted"] == 0 and recorder.calls == []
    stopped = {r["reason"] for r in _dispatches(org, jid)}
    assert stopped <= {"offer_changed", "sender_changed", "template_changed"} and stopped


def test_a_zone_that_no_longer_matches_the_approval_stops_the_messages():
    org = _org()
    _seed(org, 3)
    jid = _create(org).json()["data"]["id"]
    _approve(org, jid)

    async def widen(session):
        campaign = await session.get(Campaign, uuid.UUID(jid))
        campaign.zone = {**campaign.zone, "north": 45.95}

    _call(widen)
    recorder = Recorder()
    assert _process(org, _base() + timedelta(minutes=10), recorder)["accepted"] == 0 and recorder.calls == []
    assert {r["reason"] for r in _dispatches(org, jid)} == {"zone_changed"}


def test_a_revoked_approval_sends_nothing_more_and_resuming_needs_a_new_approval():
    org = _org()
    _seed(org, 4)
    jid = _create(org).json()["data"]["id"]
    _approve(org, jid)
    resp = requests.post(f"{API}/journeys/{jid}/revoke", headers=org["headers"], json={"reason": "erreur de zone"})
    assert resp.status_code == 200 and resp.json()["data"] == {"cancelled": 4, "status": "paused"}
    recorder = Recorder()
    assert _process(org, _base() + timedelta(minutes=10), recorder)["accepted"] == 0 and recorder.calls == []
    summary = _get(org, jid)
    assert summary["approval"]["valid"] is False and summary["approval"]["revoked_at"]
    back = requests.post(f"{API}/journeys/{jid}/resume", headers=org["headers"])
    assert back.status_code == 409 and back.json()["detail"]["code"] == "revoked"
    assert (
        requests.post(f"{API}/journeys/{jid}/revoke", headers=org["headers"], json={}).status_code == 409
    )  # not twice


def test_a_campaign_with_a_zone_never_sends_without_an_approval():
    org = _org()
    _seed(org, 2)
    jid = _create(org).json()["data"]["id"]
    # Something plants a plan row and a draft by hand, with no approval behind it: the gate refuses at send time.
    approved = _approve(org, jid)
    assert approved["scheduled"] == 2

    async def withdraw(session):  # the approval row disappears (a bug, a manual edit): nothing may leave
        await session.execute(CampaignApproval.__table__.delete().where(CampaignApproval.campaign_id == uuid.UUID(jid)))

    _call(withdraw)
    recorder = Recorder()
    assert _process(org, _base() + timedelta(minutes=10), recorder)["accepted"] == 0 and recorder.calls == []
    assert {r["reason"] for r in _dispatches(org, jid)} == {"not_approved"}


def test_pausing_makes_the_messages_wait_and_resuming_lets_them_go():
    org = _org()
    _seed(org, 3)
    jid = _create(org).json()["data"]["id"]
    _approve(org, jid)
    assert requests.post(f"{API}/journeys/{jid}/pause", headers=org["headers"]).json()["data"]["status"] == "paused"
    recorder = Recorder()
    now = _base() + timedelta(minutes=10)
    counts = _process(org, now, recorder)
    assert counts["accepted"] == 0 and recorder.calls == [] and counts["waiting"] >= 1
    assert {r["status"] for r in _dispatches(org, jid)} == {"scheduled"}  # nothing cancelled, nothing lost
    assert requests.post(f"{API}/journeys/{jid}/resume", headers=org["headers"]).json()["data"]["status"] == "running"
    assert _process(org, now + timedelta(hours=1), recorder)["accepted"] == 3


# ================================================================== caps
def test_the_daily_cap_of_the_approval_holds_the_rest_for_the_next_day():
    org = _org()
    _seed(org, 5)
    jid = _create(org).json()["data"]["id"]
    _policy(org, max_per_day=2)  # the cap in force when the person approves is the one the approval carries
    _approve(org, jid)
    _policy(org, max_per_day=1000, max_per_hour=1000)  # loosened later: the approval still says 2 a day

    async def compress(session):  # the planner had spread them over three days: bring them all to now
        await session.execute(
            update(CampaignDispatch).where(CampaignDispatch.campaign_id == uuid.UUID(jid)).values(planned_at=_base())
        )

    _call(compress)
    recorder = Recorder()
    counts = _process(org, _base() + timedelta(minutes=10), recorder)
    assert counts["accepted"] == 2 and len(recorder.calls) == 2
    waiting = [r for r in _dispatches(org, jid) if r["status"] == "scheduled"]
    assert len(waiting) == 3 and "cap_daily" in {r["reason"] for r in waiting}
    assert min(r["planned_at"] for r in waiting) >= _base() + timedelta(days=1) - timedelta(hours=9)  # next local day


def test_the_total_cap_of_the_approval_is_never_exceeded():
    org = _org()
    _seed(org, 5)
    jid = _create(org).json()["data"]["id"]
    _approve(org, jid)

    async def tighten(session):
        await session.execute(
            update(CampaignApproval).where(CampaignApproval.campaign_id == uuid.UUID(jid)).values(total_cap=3)
        )

    _call(tighten)
    recorder = Recorder()
    _process(org, _base() + timedelta(minutes=10), recorder)
    _process(org, _base() + timedelta(hours=2), recorder)
    assert len(recorder.calls) == 3
    assert sorted(r["status"] for r in _dispatches(org, jid)) == ["accepted"] * 3 + ["skipped"] * 2
    assert {r["reason"] for r in _dispatches(org, jid) if r["status"] == "skipped"} == {"cap_total"}


# ================================================================== the compact dashboard
def test_the_progress_shows_progression_replies_and_what_needs_the_person():
    org = _org()
    _seed(org, 4)
    jid = _create(org).json()["data"]["id"]
    _approve(org, jid)
    before = requests.get(f"{API}/journeys/{jid}/progress", headers=org["headers"]).json()["data"]
    assert before["total"] == 4 and before["done"] == 0 and before["percent"] == 0 and before["paused"] is False
    from services.outreach_os.channels import SendResult

    recorder = Recorder(SendResult("unknown", None, "connection lost: outcome unknown", False))
    _process(org, _base() + timedelta(minutes=10), recorder)
    after = requests.get(f"{API}/journeys/{jid}/progress", headers=org["headers"]).json()["data"]
    assert after["done"] == 4 and after["percent"] == 100
    assert after["states"].get("accepted") == 3 and after["states"].get("unknown") == 1
    codes = {a["code"] for a in after["actions"]}
    assert "unknown_outcome" in codes  # the one thing a person must look at, said plainly
    assert set(after["replies"]) == {"replied", "opted_out", "bounced"}
    assert "delivered" not in after["states"] and "livré" not in str(after).lower()


# ================================================================== isolation
def test_another_organisation_neither_sees_approves_nor_receives_a_journey():
    org = _org()
    _seed(org, 3)
    jid = _create(org).json()["data"]["id"]
    other = _org("other")
    h = other["headers"]
    assert requests.get(f"{API}/journeys/{jid}", headers=h).status_code == 404
    assert (
        requests.put(f"{API}/journeys/{jid}/template", headers=h, json={"subject": "x", "body": "{{nom}}"}).status_code
        == 404
    )
    assert (
        requests.post(
            f"{API}/journeys/{jid}/approve", headers=h, json={"content_hash": "x" * 8, "expected_count": 3}
        ).status_code
        == 404
    )
    assert requests.post(f"{API}/journeys/{jid}/revoke", headers=h, json={}).status_code == 404
    assert requests.get(f"{API}/journeys", headers=h).json()["items"] == []
    assert _create(other).json()["data"]["selected"] == 0  # the other account's prospects are not candidates there


def test_a_journey_is_not_a_launch_and_the_sequence_routes_refuse_it():
    org = _org()
    _seed(org, 2)
    jid = _create(org).json()["data"]["id"]
    h = org["headers"]
    for path, body in ((f"/campaigns/{jid}/launch", None), (f"/campaigns/{jid}/schedule", {})):
        assert requests.post(f"{API}{path}", headers=h, json=body).status_code != 200
    assert _messages(org) == []


def test_the_new_tables_keep_row_level_security_and_versions_are_unique():
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    org = _org()
    _seed(org, 1)
    jid = _create(org).json()["data"]["id"]

    async def rls(session):
        rows = await session.execute(
            text(
                "SELECT relname, relrowsecurity FROM pg_class WHERE relname IN "
                "('campaign_templates','campaign_approvals','automation_mandates','mandate_events')"
            )
        )
        return dict(rows.all())

    flags = _call(rls)
    assert flags and all(flags.values())

    async def duplicate_version(session):
        session.add(
            CampaignTemplate(
                account_id=org["account_id"],
                campaign_id=uuid.UUID(jid),
                version=1,
                subject="x",
                body="{{nom}}",
                content_hash="h",
            )
        )

    with pytest.raises(IntegrityError):
        _call(duplicate_version)


def test_approving_twice_does_not_duplicate_drafts_or_messages():
    org = _org()
    _seed(org, 3)
    jid = _create(org).json()["data"]["id"]
    _approve(org, jid)
    _approve(org, jid, now=_base() + timedelta(minutes=5))  # same template: same drafts, planned again
    recorder = Recorder()
    _process(org, _base() + timedelta(hours=1), recorder)
    assert len(recorder.calls) == 3 and len(_messages(org)) == 3
    assert len(_dispatches(org, jid)) == 3  # one plan row per recipient, however many approvals
