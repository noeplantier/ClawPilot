"""Shared rows for the tests that read the commercial map: prospects the common policy qualifies, or not on purpose.

`row(...)` builds one discovery prospect (a lead + the source that carries its address and position). Every argument
that makes it unqualified is explicit, so a test reads as the rule it checks. No network, no demo data."""

import uuid
from datetime import datetime, timedelta, timezone

from db.models import Lead, ProspectSource, SuppressionEntry
from services.outreach_os.normalize import identity_hash, normalize_email

NOW = datetime.now(timezone.utc)
UNSET = object()


def row(
    name,
    city="Lyon",
    *,
    email=UNSET,
    phone=UNSET,
    website=None,
    address="12 rue du Port",
    lat=45.76,
    lon=4.83,
    fit=72,
    scored_days=1,
    source_days=1,
    source_name="osm",
    review_status="pending",
    title="Owner",
    **lead_over,
):
    """email/phone default to realistic ones; pass None for 'not published'."""
    tag = uuid.uuid4().hex[:8]
    slug = "".join(c for c in name.lower() if c.isascii() and c.isalnum()) or "x"
    lead = {
        "full_name": name,
        "company": name,
        "city": city,
        "vertical": "restaurants",
        "country": "FR",
        "title": title,
        "email": f"{slug}.{tag}@restaurant-test.fr" if email is UNSET else email,
        "phone": f"+33 4 78 {int(tag[:4], 16) % 100:02d} {int(tag[4:], 16) % 100:02d} 01" if phone is UNSET else phone,
        "website": website,
        "review_status": review_status,
        "fit_score": fit,
        "qualification_scored_at": None if fit is None else NOW - timedelta(days=scored_days),
        "website_quality": None if fit is None else 50,
        "digital_maturity": None if fit is None else 50,
        "priority": None if fit is None else "medium",
        **lead_over,
    }
    fields = {"name": name, "city": city, "external_id": f"node/{tag}"}
    if address is not None:
        fields["address"] = address
    if lat is not None:
        fields["lat"] = lat
    if lon is not None:
        fields["lon"] = lon
    source = None
    if source_days is not None:
        source = {
            "source_name": source_name,
            "source_url": f"https://www.openstreetmap.org/node/{tag}",
            "external_id": f"node/{tag}",
            "license_note": "ODbL",
            "fetched_at": NOW - timedelta(days=source_days),
            "fields": fields,
        }
    return {"lead": lead, "source": source}


async def insert(session, account_id, rows, suppress_emails=()):
    leads = []
    for item in rows:
        lead = Lead(account_id=account_id, **item["lead"])
        session.add(lead)
        await session.flush()
        leads.append(lead)
        if item["source"]:
            session.add(
                ProspectSource(account_id=account_id, lead_id=lead.id, content_hash=uuid.uuid4().hex, **item["source"])
            )
    for email in suppress_emails:
        session.add(
            SuppressionEntry(
                account_id=account_id,
                kind="email",
                identity_hash=identity_hash("email", normalize_email(email)),
                reason="opt_out",
            )
        )
    await session.flush()
    return leads


def insert_rows(account_id, rows, suppress_emails=()):
    from tasks._bridge import run_async

    async def go(session):
        return [str(lead.id) for lead in await insert(session, account_id, rows, suppress_emails)]

    return run_async(go)
