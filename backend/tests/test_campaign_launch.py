"""Individual campaigns end to end, WITHOUT a network and without a real transport: a recording adapter stands in for
SMTP, so a message is "accepted" only in the sense that the recorder took it. Nothing is ever delivered.

The server (HTTP) creates the organisation, the selection, the review and the plan; the sending of the plan runs in this
process on the real database with an injected clock, because that is the only way to check what happens "at the moment
a message leaves". Needs DATABASE_URL (the same database as the server) and OUTREACH_SENDER_* like the other suites.
"""

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

if not os.environ.get("DATABASE_URL"):
    pytest.skip("needs DATABASE_URL (same database as the server)", allow_module_level=True)

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from db.models import (  # noqa: E402
    Campaign,
    CampaignDispatch,
    Contact,
    Lead,
    MessageDraft,
    OutboundMessage,
    ProspectSignal,
    SendPolicy,
    SignalDismissal,
)
from deps import JWT_SECRET  # noqa: E402
from repositories import campaign_repo, consent_repo, draft_repo, prospect_repo, suppression_repo  # noqa: E402
from services import campaign_launch, smtp_svc  # noqa: E402
from services.outreach_os import drafts as drafts_svc  # noqa: E402
from services.outreach_os import signals as sig  # noqa: E402
from services.outreach_os.channels import SendResult  # noqa: E402
from services.outreach_os.types import SignalResult, SignalState  # noqa: E402
from services.outreach_os.unsubscribe import make_token  # noqa: E402
from tasks._bridge import run_async  # noqa: E402
from tests.prospect_fixtures import insert_rows, row  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
CITIES = ["Lyon", "Nantes", "Lille", "Rennes", "Dijon"]


@pytest.fixture(autouse=True)
def live_env(monkeypatch):
    """A production-like configuration in THIS process only: live sending on, sandbox off, no provider configured (the
    recorder is injected), no kill switch. Each test that needs another configuration changes it itself."""
    if not all(os.environ.get(f"OUTREACH_SENDER_{k}") for k in ("NAME", "COMPANY", "ADDRESS", "EMAIL")):
        pytest.skip("needs OUTREACH_SENDER_NAME/_COMPANY/_ADDRESS/_EMAIL, the same as the server (see ci.yml)")
    monkeypatch.setenv("FEATURE_LIVE_SENDING", "true")
    monkeypatch.setenv("OUTREACH_SANDBOX", "false")
    for name in ("SEND_KILL_SWITCH", "OUTREACH_LIVE_ALLOWLIST", "SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("SENDGRID_API_KEY", raising=False)


class Recorder:
    """A real-looking adapter that records what it was asked to send, with scripted outcomes. No network."""

    channel, name, dry_run = "email", "smtp", False

    def __init__(self, *results):
        self.calls = []
        self.results = list(results)

    def send(self, message):
        self.calls.append(message)
        if self.results:
            outcome = self.results.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return SendResult("sent", f"<m{len(self.calls)}@test.example>", simulated=False)


def _register(prefix="launch"):
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"{prefix}_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Launch Tester",
            "organization_name": f"Launch Org {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = requests.get(f"{API}/auth/me", headers=headers).json()["user"]
    return {"headers": headers, "account_id": uuid.UUID(me["org_id"]), "user_id": uuid.UUID(me["id"])}


@pytest.fixture()
def org():
    org = _register()
    # Open limits and a window that holds the injected clock (09:00 UTC) whatever the recipient's country.
    _policy(org, max_per_day=1000, max_per_hour=1000, min_delay_seconds=0, timezone_source="account_default")
    return org


def _policy(org, **fields):
    async def go(session):
        found = await session.execute(
            select(SendPolicy).where(SendPolicy.account_id == org["account_id"], SendPolicy.channel == "email")
        )
        policy = found.scalar_one_or_none()
        if policy is None:
            policy = SendPolicy(account_id=org["account_id"], channel="email")
            session.add(policy)
        for key, value in fields.items():
            setattr(policy, key, value)

    run_async(go)


def _base():
    """Tomorrow 09:00 UTC: inside the 8-18 window of UTC and of Paris, and fresh enough for the qualification."""
    return (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)


def _seed(org, count, *, start=0, **over):
    rows = [
        row(f"Bistro {i:03d}", CITIES[i % len(CITIES)], review_status="approved", **over)
        for i in range(start, start + count)
    ]
    return insert_rows(org["account_id"], rows)


def _create(org, size=100, name="Lot test"):
    resp = requests.post(f"{API}/launches", headers=org["headers"], json={"name": name, "size": size})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _draft(org, lead_id, *, status="draft", facts=None, results=None, edit=None, dry_run=False):
    """What the automatic flow stores: a compliant draft, personalised from the prospect, status `draft` (a human has
    not approved it yet)."""

    async def go(session):
        lead = await session.get(Lead, uuid.UUID(lead_id))
        sender = drafts_svc.SenderIdentity.from_env()
        content = drafts_svc.render_email_draft(
            business_name=lead.full_name,
            city=lead.city,
            results=results or [],
            source_name="osm",
            last_updated=None,
            sender=sender,
            unsubscribe_url=f"http://test.example/api/unsubscribe/{make_token(JWT_SECRET, org['account_id'], lead.id)}",
        )
        body = edit(content.body) if edit else content.body
        draft, _ = await draft_repo.create_idempotent(
            session,
            org["account_id"],
            idempotency_key=f"test:{lead_id}:{uuid.uuid4().hex[:8]}",
            lead_id=lead.id,
            channel="email",
            subject=content.subject,
            body=body,
            facts=content.facts if facts is None else facts,
            template_version="test",
            status=status,
            dry_run=dry_run,
            created_by_user_id=None,
        )
        return str(draft.id)

    return run_async(go)


def _review(org, launch_id, **params):
    resp = requests.get(f"{API}/launches/{launch_id}/review", headers=org["headers"], params={"limit": 100, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _approve(org, launch_id, draft_ids):
    resp = requests.post(
        f"{API}/launches/{launch_id}/review-drafts",
        headers=org["headers"],
        json={"draft_ids": draft_ids, "decision": "approve"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ready_launch(org, count, *, size=None):
    """A campaign of `count` recipients, each with an approved draft, not planned yet."""
    ids = _seed(org, count)
    launch = _create(org, size or count)
    assert launch["selected"] == count
    launch_id = launch["launch"]["id"]
    drafts = [_draft(org, lead_id) for lead_id in ids]
    assert _approve(org, launch_id, drafts)["done"] == count
    return launch_id, ids, drafts


def _campaign_call(org, fn):
    async def go(session):
        return await fn(session)

    return run_async(go)


def _schedule(org, launch_id, expected, now=None):
    async def go(session):
        campaign = await campaign_repo.get_campaign(session, org["account_id"], launch_id)
        return await campaign_launch.schedule(
            session, org["account_id"], org["user_id"], campaign, expected=expected, now=now or _base()
        )

    return run_async(go)


def _process(org, now, adapter, limit=500):
    async def go(session):
        return await campaign_launch.process_due(
            session, now=now, live_adapter=adapter, limit=limit, account_id=org["account_id"]
        )

    return run_async(go)


def _dispatches(org, launch_id):
    async def go(session):
        rows = await session.execute(
            select(CampaignDispatch).where(
                CampaignDispatch.account_id == org["account_id"], CampaignDispatch.campaign_id == uuid.UUID(launch_id)
            )
        )
        return [
            {
                "lead_id": str(r.lead_id),
                "to": r.to_email,
                "status": r.status,
                "reason": r.last_reason,
                "planned_at": r.planned_at,
                "message_id": r.message_id,
                "attempts": r.attempts,
            }
            for r in rows.scalars()
        ]

    return run_async(go)


def _messages(org):
    async def go(session):
        rows = await session.execute(select(OutboundMessage).where(OutboundMessage.account_id == org["account_id"]))
        return [
            {
                "key": m.idempotency_key,
                "status": m.status,
                "to": m.to_email,
                "dry_run": m.dry_run,
                "lead_id": str(m.lead_id),
            }
            for m in rows.scalars()
        ]

    return run_async(go)


def _tracking(org, launch_id, **params):
    resp = requests.get(f"{API}/launches/{launch_id}/tracking", headers=org["headers"], params={"limit": 100, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _lead_names(org, ids):
    async def go(session):
        rows = await session.execute(
            select(Lead.id, Lead.full_name, Lead.email).where(Lead.id.in_([uuid.UUID(i) for i in ids]))
        )
        return {str(i): (name, email) for i, name, email in rows.all()}

    return run_async(go)


# ================================================================== the whole flow, 100 recipients
def test_a_hundred_recipients_become_a_hundred_distinct_single_recipient_messages(org):
    ids = _seed(org, 100)
    launch = _create(org, 100)
    launch_id = launch["launch"]["id"]
    assert launch["selected"] == 100 and launch["launch"]["status"] == "draft"

    # No draft yet: the review says so instead of inventing one; nothing can be planned.
    assert _review(org, launch_id)["total"] == 100
    assert _review(org, launch_id, stage="no_draft")["total"] == 100
    plan = requests.get(f"{API}/launches/{launch_id}/plan", headers=org["headers"]).json()
    assert plan["sendable"] == 0 and plan["stages"] == {"no_draft": 100}

    drafts = [_draft(org, lead_id) for lead_id in ids]
    assert _review(org, launch_id, stage="to_review")["total"] == 100
    approved = _approve(org, launch_id, drafts)
    assert approved["done"] == 100 and approved["refused"] == 0

    plan = requests.get(f"{API}/launches/{launch_id}/plan", headers=org["headers"]).json()
    assert plan["sendable"] == 100 and plan["blockers"] == []
    assert sum(day["count"] for day in plan["schedule"]["days"]) == 100

    result = _schedule(org, launch_id, 100)
    assert result["scheduled"] == 100 and result["refused"] is None
    rows = _dispatches(org, launch_id)
    assert len(rows) == 100 and {r["status"] for r in rows} == {"scheduled"}
    assert len({r["lead_id"] for r in rows}) == 100 and len({r["to"] for r in rows}) == 100
    assert _messages(org) == []  # planning sent, and wrote to the ledger, nothing

    recorder = Recorder()
    counts = _process(org, _base() + timedelta(minutes=10), recorder)
    assert counts["accepted"] == 100 and counts["failed"] == counts["unknown"] == counts["skipped"] == 0

    names = _lead_names(org, ids)
    assert len(recorder.calls) == 100
    assert {c.to for c in recorder.calls} == {email.lower() for _, email in names.values()}
    unsubscribe_links = set()
    for call in recorder.calls:
        lead_id = next(i for i, (_, email) in names.items() if email.lower() == call.to)
        name = names[lead_id][0]
        assert name in call.subject and name in call.body  # personalised to its recipient
        assert not any(other in call.body for other, _ in names.values() if other != name)  # and to nobody else
        assert "List-Unsubscribe" in call.headers
        unsubscribe_links.add(call.headers["List-Unsubscribe"])
        mime = smtp_svc.build_message(call)
        assert mime["To"] == call.to and mime["Cc"] is None and mime["Bcc"] is None  # one message per recipient
    assert len(unsubscribe_links) == 100  # each opt-out link is the recipient's own

    ledger = _messages(org)
    assert len(ledger) == 100 and len({m["key"] for m in ledger}) == 100
    assert all(m["key"].startswith("campaign:") and m["status"] == "sent" and not m["dry_run"] for m in ledger)

    tracking = _tracking(org, launch_id)
    assert tracking["total"] == 100 and tracking["counts"] == {"accepted": 100}
    assert "delivered" not in tracking["labels"] and not any("livré" in v.lower() for v in tracking["labels"].values())
    assert "livraison non prouvée" in tracking["labels"]["accepted"]

    # Idempotence: running the sender again, or planning again, produces no second message.
    assert _process(org, _base() + timedelta(hours=1), recorder)["accepted"] == 0
    assert len(recorder.calls) == 100
    assert _schedule(org, launch_id, 0)["scheduled"] == 0
    assert len(_dispatches(org, launch_id)) == 100 and len(_messages(org)) == 100


def test_default_limits_spread_a_hundred_messages_over_five_days_inside_each_recipients_window(org):
    _policy(org, max_per_day=20, max_per_hour=100, min_delay_seconds=60, timezone_source="lead_country")
    launch_id, _, _ = _ready_launch(org, 100)
    plan = requests.get(f"{API}/launches/{launch_id}/plan", headers=org["headers"]).json()
    assert plan["schedule"]["days"] and max(day["count"] for day in plan["schedule"]["days"]) <= 20
    assert len(plan["schedule"]["days"]) >= 5

    assert _schedule(org, launch_id, 100)["scheduled"] == 100
    import zoneinfo

    paris = zoneinfo.ZoneInfo("Europe/Paris")
    slots = sorted(r["planned_at"] for r in _dispatches(org, launch_id))
    assert all(8 <= s.astimezone(paris).hour < 18 for s in slots)  # French recipients: their own 8-18 window
    per_day = {}
    for slot in slots:
        per_day.setdefault(slot.astimezone(timezone.utc).date(), []).append(slot)
    assert max(len(v) for v in per_day.values()) <= 20
    assert all(b - a >= timedelta(seconds=60) for a, b in zip(slots, slots[1:]))


# ================================================================== selection
def test_selection_deduplicates_and_reports_every_exclusion_with_its_reason(org):
    good = _seed(org, 6)
    rows = [
        row("La Vieille Auberge", "Nantes", review_status="approved"),
        row("La vieille auberge", "Nantes", review_status="approved"),  # same establishment, other address
        row("Le Supprimé", "Lille", review_status="approved", email="gone@restaurant-test.fr"),
        row("Le Rejeté", "Lille", review_status="rejected"),
        row("Le Non Validé", "Lille", review_status="pending"),
        row("Le Sans Téléphone", "Lille", review_status="approved", phone=None),
    ]
    insert_rows(org["account_id"], rows, suppress_emails=["gone@restaurant-test.fr"])
    created = _create(org, 100)
    codes = {item["name"]: item["code"] for item in created["excluded"]}
    assert codes["Le Supprimé"] == "suppressed"
    assert created["not_approved"] >= 2  # the rejected and the not yet validated prospect are counted, never picked
    assert codes["Le Sans Téléphone"] == "not_qualified"
    picked = _review(org, created["launch"]["id"])["items"]
    picked_names = [item["name"] for item in picked]
    assert len(picked_names) == len(set(picked_names)) == created["selected"]
    assert not {"Le Supprimé", "Le Rejeté", "Le Non Validé", "Le Sans Téléphone"} & set(picked_names)
    # Exactly one of the pair is kept, and the reason for the other is given.
    assert len({"La Vieille Auberge", "La vieille auberge"} & set(picked_names)) == 1
    assert "duplicate_establishment" in set(codes.values())
    assert set(good) <= {item["lead_id"] for item in picked}


def test_a_prospect_held_by_another_campaign_is_not_picked_twice(org):
    _seed(org, 10)
    first = _create(org, 6, name="Premier lot")
    second = _create(org, 100, name="Second lot")
    first_ids = {item["lead_id"] for item in _review(org, first["launch"]["id"])["items"]}
    second_ids = {item["lead_id"] for item in _review(org, second["launch"]["id"])["items"]}
    assert len(first_ids) == 6 and len(second_ids) == 4 and not first_ids & second_ids
    assert {item["code"] for item in second["excluded"]} == {"campaign_conflict"}


def test_a_recipient_who_replied_bounced_or_was_contacted_is_excluded(org):
    ids = _seed(org, 4)

    async def go(session):
        for lead_id, status in zip(ids[:3], ("replied", "bounced", "sent")):
            lead = await session.get(Lead, uuid.UUID(lead_id))
            session.add(
                OutboundMessage(
                    account_id=org["account_id"],
                    lead_id=lead.id,
                    channel="email",
                    to_email=lead.email,
                    subject="avant",
                    body="avant",
                    adapter="smtp",
                    dry_run=False,
                    status=status,
                    idempotency_key=f"earlier:{lead_id}",
                    dispatched_at=datetime.now(timezone.utc) - timedelta(days=30),
                )
            )

    run_async(go)
    created = _create(org, 100)
    codes = {item["lead_id"]: item["code"] for item in created["excluded"]}
    assert codes[ids[0]] == "already_replied" and codes[ids[1]] == "bounced" and codes[ids[2]] == "already_contacted"
    assert created["selected"] == 1


def test_a_recipient_already_picked_under_another_spelling_of_its_address_is_a_duplicate():
    """The leads table already refuses two identical addresses; this is the rule behind it for the spellings it does
    not catch (spaces, case of the domain)."""
    from repositories import eligibility_sql  # noqa: F401  (the rule below is the one the selection applies)
    from services.outreach_os import provider_policy

    facts = campaign_launch.Facts(set(), set(), set(), set(), set(), {}, {})
    provider = provider_policy.identify(smtp_host=None, sendgrid_configured=False)
    lead = Lead(full_name="Chez Dupont", city="Lyon", email=" Contact@Restaurant-Test.fr ", review_status="approved")
    flags = (True, False, False, False)
    seen_emails: set = {"contact@restaurant-test.fr"}
    assert campaign_launch.exclusion_for(lead, flags, facts, provider, seen_emails, set()) == "duplicate_email"
    assert campaign_launch.exclusion_for(lead, flags, facts, provider, set(), set()) is None


# ================================================================== provider
def _hostinger(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.hostinger.com")
    monkeypatch.setenv("SMTP_USERNAME", "sender@test.example")
    monkeypatch.setenv("SMTP_PASSWORD", secrets.token_hex(8))  # generated per run: never a literal credential


def test_hostinger_only_lets_an_explicit_opt_in_receive_a_campaign(org, monkeypatch):
    _hostinger(monkeypatch)
    ids = _seed(org, 3)
    consent_basis = insert_rows(org["account_id"], [row("Base Consentie", "Lyon", review_status="approved")])[0]
    interest_basis = insert_rows(org["account_id"], [row("Base Intérêt", "Lyon", review_status="approved")])[0]

    async def go(session):
        notes = {
            consent_basis: "ODbL; legal basis: consent",
            interest_basis: "ODbL; legal basis: legitimate_interest_b2b",
        }
        for lead_id, note in notes.items():
            from db.models import ProspectSource

            found = await session.execute(select(ProspectSource).where(ProspectSource.lead_id == uuid.UUID(lead_id)))
            found.scalar_one().license_note = note
        # An explicit opt-in recorded for the first scraped prospect.
        lead = await session.get(Lead, uuid.UUID(ids[0]))
        contact = Contact(account_id=org["account_id"], lead_id=lead.id, full_name=lead.full_name, email=lead.email)
        session.add(contact)
        await session.flush()
        await consent_repo.record_consent(
            session, org["account_id"], contact.id, channel="email", status="opted_in", source="form"
        )

    run_async(go)

    async def select_now(session):
        return await campaign_launch.select_recipients(
            session, org["account_id"], size=100, now=datetime.now(timezone.utc)
        )

    selection = run_async(select_now)
    picked = {str(lead.id) for lead in selection.picked}
    assert picked == {ids[0], consent_basis}  # the opt-in and the declared consent, nobody else
    reasons = {str(e.lead_id): e.code for e in selection.excluded}
    assert reasons[ids[1]] == reasons[ids[2]] == reasons[interest_basis] == "provider_requires_opt_in"

    gates = requests.get(f"{API}/launches/provider", headers=org["headers"]).json()
    assert gates["provider"]["id"] in {"none", "smtp", "sendgrid", "smtp_hostinger"}  # the SERVER's configuration
    assert (
        gates["timezone_source"] in {"lead_country", "account_default"}
        and gates["window_start_hour"] < gates["window_end_hour"]
    )


def test_an_unknown_provider_is_flagged_but_blocks_nobody(org, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example-mail.test")
    monkeypatch.setenv("SMTP_USERNAME", "sender@test.example")
    monkeypatch.setenv("SMTP_PASSWORD", secrets.token_hex(8))
    _seed(org, 3)

    async def go(session):
        return await campaign_launch.select_recipients(
            session, org["account_id"], size=100, now=datetime.now(timezone.utc)
        )

    assert len(run_async(go).picked) == 3
    assert campaign_launch.provider_info().cold_outreach == "unverified"


def test_a_message_planned_before_the_provider_changed_is_stopped_at_send_time(org, monkeypatch):
    launch_id, _, _ = _ready_launch(org, 3)
    assert _schedule(org, launch_id, 3)["scheduled"] == 3
    _hostinger(monkeypatch)  # the provider is switched afterwards: none of these has an opt-in
    recorder = Recorder()
    counts = _process(org, _base() + timedelta(minutes=5), recorder)
    assert counts["skipped"] == 3 and recorder.calls == []
    assert {r["reason"] for r in _dispatches(org, launch_id)} == {"provider_requires_opt_in"}


# ================================================================== review: blockers
def test_unresolved_variables_and_unsourced_facts_block_the_approval(org):
    ids = _seed(org, 4)
    launch_id = _create(org, 4)["launch"]["id"]
    clean = _draft(org, ids[0])
    variable = _draft(org, ids[1], edit=lambda body: body.replace("Bonjour,", "Bonjour {{prenom}},"))
    bracket = _draft(org, ids[2], edit=lambda body: body.replace("Bonjour,", "Bonjour [Ville],"))
    invented = _draft(org, ids[3], facts=["Votre site met 12 secondes à s'afficher."])  # no signal backs it

    out = _approve(org, launch_id, [clean, variable, bracket, invented])
    assert out["done"] == 1 and out["refused"] == 3
    reasons = {r["draft_id"]: r["reason"] for r in out["results"]}
    assert "Variable non résolue" in reasons[variable] and "{{prenom}}" in reasons[variable]
    assert "[Ville]" in reasons[bracket]
    assert "Constat sans source" in reasons[invented]
    review = _review(org, launch_id)
    by_lead = {item["lead_id"]: item for item in review["items"]}
    assert by_lead[ids[0]]["stage"] == "ready"
    for lead_id in ids[1:]:
        assert by_lead[lead_id]["stage"] == "to_review"  # still waiting for a human, with its blockers shown
        assert any(p["blocking"] for p in by_lead[lead_id]["problems"])
    plan = requests.get(f"{API}/launches/{launch_id}/plan", headers=org["headers"]).json()
    assert plan["sendable"] == 1


def test_a_fact_is_sourced_while_its_signal_is_detected_and_blocks_once_it_is_dismissed(org):
    (lead_id,) = _seed(org, 1)
    results = [SignalResult(sig.NO_WEBSITE, SignalState.DETECTED, "pas de site dans l'annuaire")]

    async def detect(session):
        session.add(
            ProspectSignal(
                account_id=org["account_id"],
                lead_id=uuid.UUID(lead_id),
                signal_key=sig.NO_WEBSITE,
                state="detected",
                evidence="pas de site dans l'annuaire",
            )
        )

    run_async(detect)
    launch_id = _create(org, 1)["launch"]["id"]
    draft_id = _draft(org, lead_id, results=results)
    item = _review(org, launch_id)["items"][0]
    assert item["stage"] == "to_review" and item["problems"] == []
    assert item["evidence"]["facts"] and item["evidence"]["source"]["name"] == "osm"
    assert item["evidence"]["site_state"] == "none_identified"  # the listing was read and carried no site
    assert _approve(org, launch_id, [draft_id])["done"] == 1

    async def dismiss(session):
        session.add(
            SignalDismissal(
                account_id=org["account_id"],
                lead_id=uuid.UUID(lead_id),
                signal_key=sig.NO_WEBSITE,
                action="dismiss",
                reason="faux",
            )
        )

    run_async(dismiss)
    after = _review(org, launch_id)["items"][0]
    assert after["stage"] == "blocked"  # approved earlier, but nothing backs its claim any more
    assert [p["code"] for p in after["problems"] if p["blocking"]] == ["unsourced_fact"]
    assert after["evidence"]["site_state"] == "unknown"  # a dismissed signal is no evidence of anything
    plan = requests.get(f"{API}/launches/{launch_id}/plan", headers=org["headers"]).json()
    assert plan["sendable"] == 0 and plan["stages"] == {"blocked": 1}


def test_an_empty_field_is_never_read_as_no_website(org):
    (lead_id,) = _seed(org, 1, website=None)
    launch_id = _create(org, 1)["launch"]["id"]
    _draft(org, lead_id)
    item = _review(org, launch_id)["items"][0]
    assert item["evidence"]["site_state"] == "unknown"  # nothing was searched: unknown, not "no website"
    (with_site,) = _seed(org, 1, start=50, website="https://www.bistro-050.example")
    other = _create(org, 1, name="Autre")["launch"]["id"]
    assert [i for i in _review(org, other)["items"] if i["lead_id"] == with_site][0]["evidence"][
        "site_state"
    ] == "site_found"


def test_a_missing_or_rejected_draft_is_shown_and_cannot_be_planned(org):
    ids = _seed(org, 3)
    launch_id = _create(org, 3)["launch"]["id"]
    rejected = _draft(org, ids[0])
    approved = _draft(org, ids[1])
    resp = requests.post(
        f"{API}/launches/{launch_id}/review-drafts",
        headers=org["headers"],
        json={"draft_ids": [rejected], "decision": "reject"},
    )
    assert resp.json()["done"] == 1
    assert _approve(org, launch_id, [approved])["done"] == 1
    stages = {i["lead_id"]: i["stage"] for i in _review(org, launch_id)["items"]}
    assert stages == {ids[0]: "rejected", ids[1]: "ready", ids[2]: "no_draft"}
    assert _schedule(org, launch_id, 1)["scheduled"] == 1
    assert len(_dispatches(org, launch_id)) == 1


# ================================================================== planning
def test_the_button_refuses_a_stale_count_and_writes_nothing(org):
    launch_id, _, _ = _ready_launch(org, 5)
    resp = requests.post(f"{API}/launches/{launch_id}/schedule", headers=org["headers"], json={"expected_count": 4})
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "plan_changed"
    assert resp.json()["detail"]["actual"] == 5
    assert _dispatches(org, launch_id) == []
    ok = requests.post(f"{API}/launches/{launch_id}/schedule", headers=org["headers"], json={"expected_count": 5})
    assert ok.status_code == 200 and ok.json()["scheduled"] == 5
    assert _messages(org) == []  # planned, nothing sent


def test_planning_through_the_server_sends_nothing_and_cancel_stops_what_has_not_left(org):
    launch_id, _, _ = _ready_launch(org, 4)
    resp = requests.post(f"{API}/launches/{launch_id}/schedule", headers=org["headers"], json={"expected_count": 4})
    assert resp.status_code == 200
    tracking = _tracking(org, launch_id)
    assert tracking["counts"] == {"scheduled": 4}
    cancelled = requests.post(f"{API}/launches/{launch_id}/cancel", headers=org["headers"]).json()
    assert cancelled == {"cancelled": 4, "status": "paused"}
    recorder = Recorder()
    assert _process(org, datetime.now(timezone.utc) + timedelta(days=30), recorder)["accepted"] == 0
    assert recorder.calls == [] and _tracking(org, launch_id)["counts"] == {"cancelled": 4}


def test_the_plan_is_refused_without_a_sender_identity(org, monkeypatch):
    launch_id, _, _ = _ready_launch(org, 2)
    monkeypatch.delenv("OUTREACH_SENDER_NAME")

    async def go(session):
        campaign = await campaign_repo.get_campaign(session, org["account_id"], launch_id)
        plan, _, _ = await campaign_launch.preview(session, org["account_id"], campaign, _base())
        return plan

    plan = run_async(go)
    assert plan["sendable"] == 0  # a draft without the sender's identity is not compliant any more
    assert {b["code"] for b in plan["blockers"]} == {"sender_not_configured"}


# ================================================================== the gates, at the moment of each send
def _planned(org, count=3):
    launch_id, ids, _ = _ready_launch(org, count)
    assert _schedule(org, launch_id, count)["scheduled"] == count
    return launch_id, ids


def test_a_reply_an_opposition_a_suppression_or_a_change_stops_the_message_at_send_time(org):
    launch_id, ids = _planned(org, 7)

    async def go(session):
        replied = await session.get(Lead, uuid.UUID(ids[0]))
        session.add(
            OutboundMessage(
                account_id=org["account_id"],
                lead_id=replied.id,
                channel="email",
                to_email=replied.email,
                subject="autre",
                body="autre",
                adapter="smtp",
                dry_run=False,
                status="replied",
                idempotency_key=f"other:{replied.id}",
            )
        )
        opposed = await session.get(Lead, uuid.UUID(ids[1]))
        await prospect_repo.opt_out(session, org["account_id"], opposed, source="email_reply")
        bounced = await session.get(Lead, uuid.UUID(ids[2]))
        await suppression_repo.add(session, org["account_id"], "email", bounced.email, reason="bounce")
        rejected = await session.get(Lead, uuid.UUID(ids[3]))
        rejected.review_status = "rejected"
        moved = await session.get(Lead, uuid.UUID(ids[4]))
        moved.email = "nouvelle.adresse@restaurant-test.fr"
        edited = (
            await session.execute(
                select(MessageDraft).where(
                    MessageDraft.lead_id == uuid.UUID(ids[5]), MessageDraft.account_id == org["account_id"]
                )
            )
        ).scalar_one()
        edited.status = "draft"  # sent back for review after it was planned

    run_async(go)
    recorder = Recorder()
    counts = _process(org, _base() + timedelta(minutes=5), recorder)
    assert counts["accepted"] == 1 and counts["skipped"] == 6
    assert [c.to for c in recorder.calls] == [_lead_names(org, [ids[6]])[ids[6]][1].lower()]
    reasons = {r["lead_id"]: (r["status"], r["reason"]) for r in _dispatches(org, launch_id)}
    assert reasons[ids[0]] == ("skipped", "already_replied")
    assert reasons[ids[1]][1] in {"suppressed", "opted_out"}
    assert reasons[ids[2]] == ("skipped", "suppressed")
    assert reasons[ids[3]] == ("skipped", "prospect_not_approved")
    assert reasons[ids[4]] == ("skipped", "recipient_changed")
    assert reasons[ids[5]] == ("skipped", "draft_not_approved")
    assert reasons[ids[6]] == ("accepted", None)
    # A stopped message is not retried at the next pass.
    assert _process(org, _base() + timedelta(hours=2), recorder)["accepted"] == 0 and len(recorder.calls) == 1
    tracking = _tracking(org, launch_id)
    assert tracking["counts"] == {"accepted": 1, "skipped": 6}


def test_a_reply_after_acceptance_is_shown_as_a_reply_and_an_opt_out_as_an_opposition(org):
    launch_id, ids = _planned(org, 2)
    assert _process(org, _base() + timedelta(minutes=5), Recorder())["accepted"] == 2

    async def go(session):
        sent = (
            await session.execute(select(OutboundMessage).where(OutboundMessage.lead_id == uuid.UUID(ids[0])))
        ).scalar_one()
        sent.status = "replied"
        lead = await session.get(Lead, uuid.UUID(ids[1]))
        await prospect_repo.opt_out(session, org["account_id"], lead, source="unsubscribe_link")

    run_async(go)
    counts = _tracking(org, launch_id)["counts"]
    assert counts.get("replied") == 1 and counts.get("accepted", 0) + counts.get("opted_out", 0) == 1


@pytest.mark.parametrize(
    "setting,code",
    [("kill_switch", "kill_switch"), ("pause", "paused"), ("campaign_paused", "campaign_paused")],
)
def test_a_halt_reschedules_the_messages_and_they_leave_once_it_is_lifted(org, monkeypatch, setting, code):
    launch_id, _ = _planned(org, 3)
    now = _base() + timedelta(minutes=5)
    if setting == "kill_switch":
        monkeypatch.setenv("SEND_KILL_SWITCH", "true")
    elif setting == "pause":
        _policy(org, sending_paused=True)
    else:

        async def pause(session):
            campaign = await session.get(Campaign, uuid.UUID(launch_id))
            campaign.status = "paused"

        run_async(pause)
    recorder = Recorder()
    counts = _process(org, now, recorder)
    assert recorder.calls == [] and counts["accepted"] == 0 and counts["waiting"] >= 1
    rows = _dispatches(org, launch_id)
    assert {r["status"] for r in rows} == {"scheduled"}  # nothing is lost, nothing is failed
    waiting = [r for r in rows if r["reason"] == code]
    assert waiting and all(r["planned_at"] >= now + timedelta(minutes=10) for r in waiting)
    # Lifted: a later pass sends all three.
    monkeypatch.delenv("SEND_KILL_SWITCH", raising=False)
    _policy(org, sending_paused=False)

    async def resume(session):
        campaign = await session.get(Campaign, uuid.UUID(launch_id))
        campaign.status = "running"

    run_async(resume)
    later = now + timedelta(hours=1)
    assert _process(org, later, recorder)["accepted"] == 3 and len(recorder.calls) == 3


def test_outside_the_window_the_message_waits_for_the_next_opening(org):
    launch_id, _ = _planned(org, 2)
    evening = _base().replace(hour=22)  # 22:00 UTC: outside the 8-18 window
    _policy(org, min_delay_seconds=0)
    recorder = Recorder()
    counts = _process(org, evening, recorder)
    assert recorder.calls == [] and counts["waiting"] >= 1
    rows = _dispatches(org, launch_id)
    assert all(r["status"] == "scheduled" and r["reason"] == "outside_window" for r in rows if r["reason"])
    assert min(r["planned_at"] for r in rows if r["reason"]) == _base().replace(hour=8) + timedelta(days=1)


def test_the_daily_limit_is_checked_again_at_send_time_and_counts_other_sends(org):
    launch_id, _ = _planned(org, 4)
    _policy(org, max_per_day=2)  # tightened after the plan was written
    recorder = Recorder()
    counts = _process(org, _base() + timedelta(minutes=5), recorder)
    assert counts["accepted"] == 2 and len(recorder.calls) == 2
    rows = _dispatches(org, launch_id)
    assert sorted(r["status"] for r in rows) == ["accepted", "accepted", "scheduled", "scheduled"]
    # The first refusal ends the run for the organisation: that message waits (reason kept), the rest keep their time.
    assert "limit_daily" in {r["reason"] for r in rows if r["status"] == "scheduled"}


def test_the_sandbox_allowlist_lets_only_listed_recipients_through(org, monkeypatch):
    launch_id, ids = _planned(org, 3)
    names = _lead_names(org, ids)
    monkeypatch.setenv("OUTREACH_SANDBOX", "true")
    monkeypatch.setenv("OUTREACH_LIVE_ALLOWLIST", names[ids[0]][1])
    recorder = Recorder()
    counts = _process(org, _base() + timedelta(minutes=5), recorder)
    assert counts["accepted"] == 1 and counts["skipped"] == 2
    assert [c.to for c in recorder.calls] == [names[ids[0]][1].lower()]
    assert {r["reason"] for r in _dispatches(org, launch_id) if r["status"] == "skipped"} == {"sandbox_recipient"}


def test_live_sending_without_an_adapter_refuses_and_keeps_the_messages(org):
    launch_id, _ = _planned(org, 2)
    counts = _process(org, _base() + timedelta(minutes=5), None)  # FEATURE_LIVE_SENDING=true, no SMTP configured
    assert counts["accepted"] == 0 and counts["waiting"] >= 1
    assert {r["status"] for r in _dispatches(org, launch_id)} == {"scheduled"}
    assert _messages(org) == []


def test_the_default_dry_run_simulates_and_is_never_called_accepted_by_smtp(org, monkeypatch):
    monkeypatch.delenv("FEATURE_LIVE_SENDING")
    launch_id, _ = _planned(org, 2)
    assert _process(org, _base() + timedelta(minutes=5), None)["accepted"] == 2
    assert all(m["dry_run"] for m in _messages(org))
    assert _tracking(org, launch_id)["counts"] == {"simulated": 2}


# ================================================================== ambiguous outcomes
def test_an_unclear_provider_result_is_never_retried(org):
    launch_id, ids = _planned(org, 3)
    recorder = Recorder(
        SendResult("unknown", None, "connection lost after DATA", False),
        RuntimeError("adapter exploded"),
        SendResult("failed", None, "550 mailbox unavailable", False),
    )
    counts = _process(org, _base() + timedelta(minutes=5), recorder)
    assert counts["unknown"] == 2 and counts["failed"] == 1 and counts["accepted"] == 0
    assert len(recorder.calls) == 3
    again = _process(org, _base() + timedelta(days=3), recorder)  # days later, with the provider healthy again
    assert sum(again[k] for k in ("accepted", "failed", "unknown", "skipped")) == 0 and len(recorder.calls) == 3
    states = {r["status"] for r in _dispatches(org, launch_id)}
    assert states == {"unknown", "failed"}
    tracking = _tracking(org, launch_id)["counts"]
    assert tracking == {"unknown": 2, "failed": 1}
    assert {m["status"] for m in _messages(org)} == {"sending", "failed"}  # the unknown one stays "sending"


def test_a_message_left_sending_by_a_crash_is_settled_from_the_ledger_and_never_sent_twice(org):
    launch_id, ids = _planned(org, 2)
    now = _base() + timedelta(minutes=5)

    async def crash(session):
        rows = (
            await session.execute(select(CampaignDispatch).where(CampaignDispatch.campaign_id == uuid.UUID(launch_id)))
        ).scalars()
        for n, dispatch_row in enumerate(rows):
            dispatch_row.status = "sending"
            dispatch_row.updated_at = now - timedelta(hours=1)
            if n == 0:  # this one reached the provider: the ledger has it
                lead = await session.get(Lead, dispatch_row.lead_id)
                session.add(
                    OutboundMessage(
                        account_id=org["account_id"],
                        lead_id=lead.id,
                        draft_id=dispatch_row.draft_id,
                        channel="email",
                        to_email=lead.email,
                        subject="s",
                        body="b",
                        adapter="smtp",
                        dry_run=False,
                        status="sent",
                        idempotency_key=f"campaign:{dispatch_row.id}",
                    )
                )

    run_async(crash)
    recorder = Recorder()
    counts = _process(org, now, recorder)
    assert counts["reconciled"] == 2
    assert len(recorder.calls) == 1  # only the one with no trace in the ledger was sent, once
    assert sorted(r["status"] for r in _dispatches(org, launch_id)) == ["accepted", "accepted"]
    assert len({m["key"] for m in _messages(org)}) == 2


def test_two_passes_at_once_cannot_claim_the_same_message(org):
    from repositories import launch_repo

    launch_id, _ = _planned(org, 1)
    now = _base() + timedelta(minutes=5)

    async def go(session):
        row = (
            await session.execute(select(CampaignDispatch).where(CampaignDispatch.campaign_id == uuid.UUID(launch_id)))
        ).scalar_one()
        first = await launch_repo.claim(session, row.id, now)
        second = await launch_repo.claim(session, row.id, now)
        return first is not None, second is None

    assert run_async(go) == (True, True)


# ================================================================== isolation and legacy paths
def test_organisations_never_see_nor_send_each_others_campaigns(org):
    launch_id, _, _ = _ready_launch(org, 3)
    other = _register("other")
    assert requests.get(f"{API}/launches/{launch_id}", headers=other["headers"]).status_code == 404
    assert requests.get(f"{API}/launches/{launch_id}/review", headers=other["headers"]).status_code == 404
    assert requests.post(f"{API}/launches/{launch_id}/cancel", headers=other["headers"]).status_code == 404
    assert (
        requests.post(
            f"{API}/launches/{launch_id}/schedule", headers=other["headers"], json={"expected_count": 3}
        ).status_code
        == 404
    )
    assert requests.get(f"{API}/launches", headers=other["headers"]).json() == []
    assert _schedule(org, launch_id, 3)["scheduled"] == 3
    recorder = Recorder()
    # The other organisation's pass, restricted to it, finds nothing of this one's.
    assert _process(other, _base() + timedelta(minutes=5), recorder)["accepted"] == 0 and recorder.calls == []
    assert _process(org, _base() + timedelta(minutes=5), recorder)["accepted"] == 3
    # The other organisation's prospects are never candidates here.
    _seed(other, 5)
    assert _create(org, 100, name="Encore")["selected"] == 0


def test_the_legacy_campaign_routes_refuse_an_individual_campaign(org):
    launch_id, _, _ = _ready_launch(org, 2)
    h = org["headers"]
    for path, body in (
        (f"/campaigns/{launch_id}/launch", None),
        (f"/campaigns/{launch_id}/schedule", {}),
        (f"/campaigns/{launch_id}/leads", {"lead_ids": []}),
    ):
        resp = requests.post(f"{API}{path}", headers=h, json=body)
        assert resp.status_code in (404, 405, 409, 422), (path, resp.status_code)
        assert resp.status_code != 200, path
    assert _messages(org) == []


def test_the_new_table_keeps_row_level_security_and_one_active_message_per_prospect(org):
    launch_id, ids = _planned(org, 1)

    async def rls(session):
        return (
            await session.execute(text("SELECT relrowsecurity FROM pg_class WHERE relname = 'campaign_dispatches'"))
        ).scalar_one()

    assert run_async(rls) is True

    async def second_active_message(session):
        existing = (
            await session.execute(select(CampaignDispatch).where(CampaignDispatch.campaign_id == uuid.UUID(launch_id)))
        ).scalar_one()
        other_campaign = Campaign(
            account_id=org["account_id"], name="autre", status="draft", kind="individual", channels=["email"]
        )
        session.add(other_campaign)
        await session.flush()
        session.add(
            CampaignDispatch(
                account_id=org["account_id"],
                campaign_id=other_campaign.id,
                lead_id=existing.lead_id,
                to_email=existing.to_email,
                status="scheduled",
                planned_at=datetime.now(timezone.utc),
            )
        )

    with pytest.raises(IntegrityError):  # the partial unique index: a prospect has at most one active message
        run_async(second_active_message)


def test_the_plan_says_when_the_allowlist_restricts_nobody(org, monkeypatch):
    """The owner's snapshot: live sending on, sandbox off, two allowlist entries. Those two entries restrict nobody, and
    the plan must say so instead of letting "2 allowed addresses" read as a limit."""
    launch_id, _, _ = _ready_launch(org, 2)
    monkeypatch.setenv("OUTREACH_SANDBOX", "false")
    monkeypatch.setenv("OUTREACH_LIVE_ALLOWLIST", "founder@plantiers.example, @team.example")

    async def go(session):
        campaign = await campaign_repo.get_campaign(session, org["account_id"], launch_id)
        plan, _, _ = await campaign_launch.preview(session, org["account_id"], campaign, _base())
        return plan

    warnings = {w["code"]: w["label"] for w in run_async(go)["warnings"]}
    assert "allowlist_inactive" in warnings and "INACTIVE" in warnings["allowlist_inactive"]
    assert "sandbox" not in warnings and "sandbox_allowlist" not in warnings
    monkeypatch.setenv("OUTREACH_SANDBOX", "true")
    assert "sandbox_allowlist" in {w["code"] for w in run_async(go)["warnings"]}
