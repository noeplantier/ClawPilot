"""The SQL policy (`repositories/eligibility_sql`) and the Python policy (`services/outreach_os/eligibility`) agree.

Each scenario is stored for real in PostgreSQL (no network). The ids the SQL keeps are compared with what the Python
policy decides on the same rows, so the map, the lists and the counters can never disagree. Needs DATABASE_URL."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from db.models import Account, ConsentCurrent, Contact, Lead, ProspectSignal, ProspectSource, SuppressionEntry
from repositories import eligibility_sql, suppression_repo
from services.outreach_os import eligibility as policy
from services.outreach_os.normalize import identity_hash, normalize_domain, normalize_email, normalize_phone
from tasks._bridge import run_async

NOW = datetime.now(timezone.utc)
FULL_SOURCE = {"address": "12 rue du Port", "lat": 48.5, "lon": -2.7}


def _ago(days):
    return NOW - timedelta(days=days)


def base(**over):
    spec = {
        "lead": {
            "email": "contact@chez-alice.fr",
            "phone": "+33 6 12 34 56 78",
            "website": None,
            "fit_score": 70,
            "scored": _ago(1),
            "review_status": "pending",
        },
        "sources": [{"fields": dict(FULL_SOURCE), "fetched": _ago(1)}],
        "signals": [],
        "suppress": [],
        "opted_out": False,
        "expect": "qualified",
    }
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(spec.get(key), dict):
            spec[key] = {**spec[key], **value}
        else:
            spec[key] = value
    return spec


def src(**over):
    return {"fields": dict(FULL_SOURCE), "fetched": _ago(1), **over}


SCENARIOS = {
    "complete without website": base(),
    "complete with website": base(lead={"website": "https://www.chez-alice.fr/carte"}),
    "no whatsapp proof needed (plain phone)": base(lead={"phone": "02 96 00 11 22"}),
    "international 00 prefix": base(lead={"phone": "0033612345678"}),
    "missing email": base(lead={"email": None}, expect="to_enrich"),
    "invalid email": base(lead={"email": "not-an-email"}, expect="to_enrich"),
    "placeholder email domain": base(lead={"email": "x@example.com"}, expect="to_enrich"),
    "gmail business is fine": base(lead={"email": "boucherie.rennes35@gmail.com"}),
    "missing phone": base(lead={"phone": None}, expect="to_enrich"),
    "unreadable phone": base(lead={"phone": "12345"}, expect="to_enrich"),
    "missing address": base(sources=[src(fields={"lat": 48.5, "lon": -2.7})], expect="to_enrich"),
    "unknown address": base(sources=[src(fields={**FULL_SOURCE, "address": "unknown"})], expect="to_enrich"),
    "short address": base(sources=[src(fields={**FULL_SOURCE, "address": "12"})], expect="to_enrich"),
    "malformed address type": base(sources=[src(fields={**FULL_SOURCE, "address": 12})], expect="to_enrich"),
    "missing coordinates": base(sources=[src(fields={"address": "12 rue du Port"})], expect="to_enrich"),
    "text coordinates": base(sources=[src(fields={**FULL_SOURCE, "lat": "48.5"})], expect="to_enrich"),
    "null island": base(sources=[src(fields={**FULL_SOURCE, "lat": 0, "lon": 0})], expect="to_enrich"),
    "latitude out of range": base(sources=[src(fields={**FULL_SOURCE, "lat": 95})], expect="to_enrich"),
    "no source": base(sources=[], expect="to_enrich"),
    "stale source": base(sources=[src(fetched=_ago(60))], expect="to_enrich"),
    "fresh real source beside a stale one": base(sources=[src(fetched=_ago(60)), src()]),
    "fit missing": base(lead={"fit_score": None, "scored": None}, expect="to_enrich"),
    "fit low": base(lead={"fit_score": 40}, expect="to_enrich"),
    "fit exactly at the minimum": base(lead={"fit_score": 60}),
    "fit stale": base(lead={"scored": _ago(60)}, expect="to_enrich"),
    "demo source only": base(sources=[src(source_name="fixture_directory")], expect="excluded"),
    "demo beside a real source": base(sources=[src(), src(source_name="world_fixture")], expect="excluded"),
    "fictional licence note is demo data": base(sources=[src(license_note="fictional data")], expect="excluded"),
    "rejected": base(lead={"review_status": "rejected"}, expect="excluded"),
    "suppressed by e-mail": base(suppress=["email"], expect="excluded"),
    "suppressed by phone": base(suppress=["phone"], expect="excluded"),
    "suppressed by website domain": base(
        lead={"website": "https://www.chez-alice.fr"}, suppress=["domain"], expect="excluded"
    ),
    "opted out": base(opted_out=True, expect="excluded"),
    "intent with evidence": base(
        signals=[{"evidence": "Asked for a quote on the contact page", "age": 2}], expect="hot"
    ),
    "intent without evidence": base(signals=[{"evidence": "  ", "age": 2}]),
    "stale intent": base(signals=[{"evidence": "Asked for a quote", "age": 90}]),
    "intent on a prospect that is not qualified": base(
        lead={"email": None}, signals=[{"evidence": "Asked for a quote", "age": 2}], expect="to_enrich"
    ),
}


def _unique(email):
    """One e-mail per lead and organisation (a unique key); the suffix keeps the syntax valid or invalid as written."""
    tag = uuid.uuid4().hex[:6]
    if email is None:
        return None
    return email.replace("@", f"+{tag}@", 1) if "@" in email else f"{email}{tag}"


async def _seed(session, account_id, name, spec):
    lead_spec = spec["lead"]
    lead = Lead(
        account_id=account_id,
        full_name=f"{name} {uuid.uuid4().hex[:6]}",
        email=_unique(lead_spec["email"]),
        phone=lead_spec["phone"],
        website=lead_spec["website"],
        city="Plérin",
        company=name,
        vertical="restaurants",
        country="FR",
        review_status=lead_spec["review_status"],
        fit_score=lead_spec["fit_score"],
        qualification_scored_at=lead_spec["scored"],
        website_quality=None if lead_spec["fit_score"] is None else 50,
        digital_maturity=None if lead_spec["fit_score"] is None else 50,
        priority=None if lead_spec["fit_score"] is None else "medium",
    )
    session.add(lead)
    await session.flush()
    rows = []
    for item in spec["sources"]:
        row = ProspectSource(
            account_id=account_id,
            lead_id=lead.id,
            source_name=item.get("source_name", "osm"),
            source_url=item.get("source_url", "https://www.openstreetmap.org/node/1"),
            external_id=uuid.uuid4().hex,
            license_note=item.get("license_note", "ODbL"),
            content_hash=uuid.uuid4().hex,
            fields=item["fields"],
            fetched_at=item["fetched"],
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    for sig in spec["signals"]:
        session.add(
            ProspectSignal(
                account_id=account_id,
                lead_id=lead.id,
                source_id=rows[0].id,
                signal_key="commercial_intent",
                state="detected",
                evidence=sig["evidence"],
                created_at=_ago(sig["age"]),
            )
        )
    for kind in spec["suppress"]:
        value = {
            "email": normalize_email(lead.email),
            "phone": normalize_phone(lead.phone),
            "domain": normalize_domain(lead.website),
        }[kind]
        session.add(
            SuppressionEntry(
                account_id=account_id, kind=kind, identity_hash=identity_hash(kind, value), reason="opt_out"
            )
        )
    if spec["opted_out"]:
        contact = Contact(account_id=account_id, lead_id=lead.id, full_name="C", email=lead.email)
        session.add(contact)
        await session.flush()
        session.add(ConsentCurrent(contact_id=contact.id, channel="email", status="opted_out"))
    await session.flush()
    return lead.id, rows


async def _python_decision(session, account_id, lead_id):
    lead = await session.get(Lead, lead_id)
    sources = (await session.execute(select(ProspectSource).where(ProspectSource.lead_id == lead_id))).scalars().all()
    signals = (await session.execute(select(ProspectSignal).where(ProspectSignal.lead_id == lead_id))).scalars().all()
    is_suppressed = await suppression_repo.is_suppressed(
        session,
        account_id,
        email=normalize_email(lead.email),
        phone=normalize_phone(lead.phone),
        domain=normalize_domain(lead.website),
    )
    contacts = (await session.execute(select(Contact.id).where(Contact.lead_id == lead_id))).scalars().all()
    opted = False
    for contact_id in contacts:
        row = await session.get(ConsentCurrent, (contact_id, "email"))
        opted = opted or bool(row and row.status == "opted_out")
    return policy.evaluate(
        {
            c: getattr(lead, c)
            for c in ("full_name", "email", "phone", "fit_score", "qualification_scored_at", "review_status")
        },
        sources=[
            {
                "id": s.id,
                "source_name": s.source_name,
                "source_url": s.source_url,
                "license_note": s.license_note,
                "fetched_at": s.fetched_at,
                "fields": s.fields,
            }
            for s in sources
        ],
        signals=[
            {
                "signal_key": g.signal_key,
                "state": g.state,
                "evidence": g.evidence,
                "source_id": g.source_id,
                "created_at": g.created_at,
            }
            for g in signals
        ],
        suppressed=is_suppressed,
        opted_out=opted,
        now=NOW,
    )


def _run_all():
    """One organisation per scenario: a suppression or an e-mail of one case can never leak into another."""

    async def one(session, name, spec):
        account = Account(name=f"parity {uuid.uuid4().hex[:8]}")
        session.add(account)
        await session.flush()
        lead_id, _ = await _seed(session, account.id, name, spec)
        latest = eligibility_sql.latest_source(account.id)
        where = [Lead.account_id == account.id]
        qualified = (
            (
                await session.execute(
                    select(Lead.id)
                    .outerjoin(latest, latest.c.lead_id == Lead.id)
                    .where(*where, eligibility_sql.qualified(latest, NOW))
                )
            )
            .scalars()
            .all()
        )
        hot = (
            (
                await session.execute(
                    select(Lead.id)
                    .outerjoin(latest, latest.c.lead_id == Lead.id)
                    .where(*where, eligibility_sql.hot(latest, NOW))
                )
            )
            .scalars()
            .all()
        )
        return lead_id, await _python_decision(session, account.id, lead_id), set(qualified), set(hot)

    async def go(session):
        out = {name: await one(session, name, spec) for name, spec in SCENARIOS.items()}
        stranger = Account(name=f"parity stranger {uuid.uuid4().hex[:8]}")
        session.add(stranger)
        await session.flush()
        stranger_lead, _ = await _seed(session, stranger.id, "stranger", base())
        mine = Account(name=f"parity mine {uuid.uuid4().hex[:8]}")
        session.add(mine)
        await session.flush()
        await _seed(session, mine.id, "mine", base())
        latest = eligibility_sql.latest_source(mine.id)
        seen = set(
            (
                await session.execute(
                    select(Lead.id)
                    .outerjoin(latest, latest.c.lead_id == Lead.id)
                    .where(eligibility_sql.qualified(latest, NOW))
                )
            ).scalars()
        )
        return out, stranger_lead, seen

    return run_async(go)


@pytest.fixture(scope="module")
def outcome():
    return _run_all()


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_python_and_sql_decide_the_same_and_match_the_expectation(outcome, name):
    scenarios, _, _ = outcome
    lead_id, decision, sql_qualified, sql_hot = scenarios[name]
    expected = SCENARIOS[name]["expect"]
    assert (lead_id in sql_qualified) == decision["eligible"], f"SQL and Python disagree: {decision}"
    assert (lead_id in sql_hot) == decision["is_hot"], f"hot disagrees: {decision}"
    assert decision["status"] == ("qualified" if expected == "hot" else expected), decision
    assert decision["is_hot"] == (expected == "hot")


def test_the_account_filter_comes_from_the_sql_not_from_the_caller(outcome):
    _, stranger_lead, seen = outcome
    assert (
        stranger_lead not in seen
    )  # `qualified` was applied WITHOUT an account filter on leads: the source join isolates


def test_missing_fields_say_what_to_enrich(outcome):
    decisions = {name: row[1] for name, row in outcome[0].items()}
    assert decisions["missing email"]["missing_fields"] == ["email_missing"]
    assert decisions["invalid email"]["missing_fields"] == ["email_invalid"]
    assert decisions["missing address"]["missing_fields"] == ["address_missing"]
    assert decisions["null island"]["missing_fields"] == ["coordinates_missing"]
    assert decisions["stale source"]["missing_fields"] == ["source_stale"]
    assert decisions["fit low"]["missing_fields"] == ["fit_low"]
    assert decisions["no source"]["missing_fields"] == ["address_missing", "coordinates_missing", "source_missing"]
    assert decisions["suppressed by e-mail"]["reasons"] == ["suppressed"]
    assert decisions["demo source only"]["reasons"] == ["demo_data"]


def test_a_site_or_whatsapp_proof_changes_nothing(outcome):
    decisions = {name: row[1] for name, row in outcome[0].items()}
    assert decisions["complete without website"]["eligible"] and decisions["complete with website"]["eligible"]
    assert decisions["complete without website"]["priority"] == "qualified"
    assert decisions["intent with evidence"]["priority"] == "hot"
    assert decisions["intent with evidence"]["priority_label"].startswith("Hot")
    assert decisions["complete without website"]["priority_label"] == "Qualifié prioritaire"
