"""One-shot migration: MongoDB collections → PostgreSQL tables.

Read-only on Mongo. Reuses existing Mongo UUIDs as Postgres primary keys (both
already use `str(uuid.uuid4())` — see legacy `models.py: _uid()`), so related
rows keep their foreign keys without any ID remapping.

Idempotent: every insert is guarded by "does a row with this id already exist?"
so the script can be re-run safely (e.g. after fixing a data issue) without
creating duplicates.

Usage:
    DATABASE_URL=postgresql+asyncpg://... MONGO_URL=mongodb://... DB_NAME=... \\
        python scripts/migrate_mongo_to_postgres.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from db.models import (  # noqa: E402
    Account,
    Agent,
    AuditLog,
    Campaign,
    CampaignLead,
    CampaignStep,
    Contact,
    EmailSend,
    Lead,
    LeadSource,
    User,
    WhatsappSend,
)
from db.session import AsyncSessionLocal  # noqa: E402


def _uid(s: str) -> uuid.UUID:
    return uuid.UUID(s)


def _dt(iso: str | None):
    from datetime import datetime

    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")) if isinstance(iso, str) else iso


async def _exists(session: AsyncSession, model, id_: uuid.UUID) -> bool:
    result = await session.execute(select(model.id).where(model.id == id_))
    return result.scalar_one_or_none() is not None


async def migrate_accounts_and_users(session: AsyncSession, mdb, dry_run: bool) -> dict:
    counts = {"accounts": 0, "users": 0}
    async for org in mdb.organizations.find({}, {"_id": 0}):
        oid = _uid(org["id"])
        if await _exists(session, Account, oid):
            continue
        counts["accounts"] += 1
        if not dry_run:
            session.add(Account(id=oid, name=org["name"], plan=org.get("plan", "pro")))
    if not dry_run:
        await session.flush()

    async for u in mdb.users.find({}, {"_id": 0}):
        uid_ = _uid(u["id"])
        if await _exists(session, User, uid_):
            continue
        counts["users"] += 1
        if not dry_run:
            session.add(
                User(
                    id=uid_,
                    account_id=_uid(u["org_id"]),
                    email=u["email"].lower(),
                    password_hash=u["password_hash"],
                    full_name=u["full_name"],
                    role=u.get("role", "owner"),
                )
            )
    if not dry_run:
        await session.flush()
    return counts


async def _resolve_source(
    session: AsyncSession, account_id: uuid.UUID, name: str | None, cache: dict
) -> uuid.UUID | None:
    if not name:
        return None
    key = (account_id, name)
    if key in cache:
        return cache[key]
    result = await session.execute(
        select(LeadSource.id).where(LeadSource.account_id == account_id, LeadSource.name == name)
    )
    source_id = result.scalar_one_or_none()
    if not source_id:
        source = LeadSource(account_id=account_id, name=name, kind="manual")
        session.add(source)
        await session.flush()
        source_id = source.id
    cache[key] = source_id
    return source_id


async def migrate_leads(session: AsyncSession, mdb, dry_run: bool) -> dict:
    counts = {"leads": 0, "contacts": 0, "lead_sources": 0}
    source_cache: dict = {}
    async for lead in mdb.leads.find({}, {"_id": 0}):
        lid = _uid(lead["id"])
        if await _exists(session, Lead, lid):
            continue
        account_id = _uid(lead["org_id"])
        source_id = None
        if lead.get("source"):
            before = len(source_cache)
            source_id = await _resolve_source(session, account_id, lead["source"], source_cache)
            if len(source_cache) > before:
                counts["lead_sources"] += 1
        counts["leads"] += 1
        if not dry_run:
            session.add(
                Lead(
                    id=lid,
                    account_id=account_id,
                    full_name=lead["full_name"],
                    email=lead.get("email"),
                    phone=lead.get("phone"),
                    company=lead.get("company"),
                    title=lead.get("title"),
                    country=lead.get("country"),
                    language=lead.get("language", "en"),
                    stage=lead.get("stage", "new"),
                    tags=lead.get("tags") or [],
                    source_id=source_id,
                    notes=lead.get("notes"),
                    score=lead.get("score", 0),
                    created_at=_dt(lead.get("created_at")),
                )
            )
            # 1:1 primary contact, mirrors the lead's own contact details (plan doc section 1.6)
            session.add(
                Contact(
                    account_id=account_id,
                    lead_id=lid,
                    full_name=lead["full_name"],
                    email=lead.get("email"),
                    phone=lead.get("phone"),
                    is_primary=True,
                )
            )
            counts["contacts"] += 1
    if not dry_run:
        await session.flush()
    return counts


async def migrate_campaigns(session: AsyncSession, mdb, dry_run: bool) -> dict:
    counts = {"campaigns": 0, "campaign_steps": 0, "campaign_leads": 0}
    async for c in mdb.campaigns.find({}, {"_id": 0}):
        cid = _uid(c["id"])
        if await _exists(session, Campaign, cid):
            continue
        counts["campaigns"] += 1
        if dry_run:
            continue
        campaign = Campaign(
            id=cid,
            account_id=_uid(c["org_id"]),
            name=c["name"],
            goal=c.get("goal"),
            status=c.get("status", "draft"),
            channels=c.get("channels") or ["email"],
            agent_id=_uid(c["agent_id"]) if c.get("agent_id") else None,
            sent=c.get("sent", 0),
            opened=c.get("opened", 0),
            replied=c.get("replied", 0),
            converted=c.get("converted", 0),
            created_at=_dt(c.get("created_at")),
        )
        session.add(campaign)
        await session.flush()
        for idx, step in enumerate(c.get("steps") or []):
            session.add(
                CampaignStep(
                    campaign_id=cid,
                    step_index=idx,
                    channel=step.get("channel", "email"),
                    delay_hours=step.get("delay_hours", 0),
                    subject=step.get("subject"),
                    body=step.get("body", ""),
                    language=step.get("language", "en"),
                )
            )
            counts["campaign_steps"] += 1
        for lead_id in c.get("lead_ids") or []:
            session.add(CampaignLead(campaign_id=cid, lead_id=_uid(lead_id)))
            counts["campaign_leads"] += 1
    if not dry_run:
        await session.flush()
    return counts


async def migrate_agents(session: AsyncSession, mdb, dry_run: bool) -> dict:
    counts = {"agents": 0}
    async for a in mdb.agents.find({}, {"_id": 0}):
        aid = _uid(a["id"])
        if await _exists(session, Agent, aid):
            continue
        counts["agents"] += 1
        if not dry_run:
            session.add(
                Agent(
                    id=aid,
                    account_id=_uid(a["org_id"]),
                    name=a["name"],
                    role=a.get("role", "outreach"),
                    status=a.get("status", "idle"),
                    tasks_completed=a.get("tasks_completed", 0),
                    tasks_in_queue=a.get("tasks_in_queue", 0),
                    created_at=_dt(a.get("created_at")),
                )
            )
    if not dry_run:
        await session.flush()
    return counts


async def migrate_messages(session: AsyncSession, mdb, dry_run: bool) -> dict:
    counts = {"email_sends": 0, "whatsapp_sends": 0}
    async for m in mdb.messages.find({}, {"_id": 0}):
        mid = _uid(m["id"])
        account_id = _uid(m["org_id"]) if m.get("org_id") else None
        campaign_id = _uid(m["campaign_id"]) if m.get("campaign_id") else None
        if m.get("channel") == "email":
            if await _exists(session, EmailSend, mid):
                continue
            counts["email_sends"] += 1
            if not dry_run:
                session.add(
                    EmailSend(
                        id=mid,
                        account_id=account_id,
                        campaign_id=campaign_id,
                        to_email=m["to"],
                        subject=m.get("subject"),
                        body=m.get("body", ""),
                        status=m.get("status", "queued"),
                        provider_message_id=m.get("provider_id"),
                        error=m.get("error"),
                        created_at=_dt(m.get("created_at")),
                    )
                )
        else:
            if await _exists(session, WhatsappSend, mid):
                continue
            counts["whatsapp_sends"] += 1
            if not dry_run:
                session.add(
                    WhatsappSend(
                        id=mid,
                        account_id=account_id,
                        campaign_id=campaign_id,
                        direction=m.get("direction", "outbound"),
                        from_number="",
                        to_number=m["to"],
                        body=m.get("body", ""),
                        status=m.get("status", "queued"),
                        provider_message_sid=m.get("provider_id"),
                        error=m.get("error"),
                        created_at=_dt(m.get("created_at")),
                    )
                )
    if not dry_run:
        await session.flush()
    return counts


async def migrate_activity(session: AsyncSession, mdb, dry_run: bool) -> dict:
    """`activity` docs have no stable `id` matching a Postgres PK to dedupe
    against (they used a generated uuid too, but re-running would create
    duplicates since AuditLog is append-only with no unique constraint on
    content) — guarded instead by only running when audit_logs is still empty,
    since this is a one-shot historical import, not an ongoing sync."""
    counts = {"audit_logs": 0}
    result = await session.execute(select(AuditLog.id).limit(1))
    if result.scalar_one_or_none() is not None:
        return counts
    async for a in mdb.activity.find({}, {"_id": 0}):
        if not a.get("org_id"):
            continue
        counts["audit_logs"] += 1
        if not dry_run:
            session.add(
                AuditLog(
                    account_id=_uid(a["org_id"]),
                    actor_type="system",
                    action=a.get("kind", "unknown"),
                    resource_type="activity",
                    diff={"title": a.get("title"), "meta": a.get("meta")},
                    created_at=_dt(a.get("created_at")),
                )
            )
    if not dry_run:
        await session.flush()
    return counts


async def main(dry_run: bool) -> None:
    mongo_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    mdb = mongo_client[os.environ["DB_NAME"]]

    all_counts: dict = {}
    async with AsyncSessionLocal() as session:
        all_counts.update(await migrate_accounts_and_users(session, mdb, dry_run))
        all_counts.update(await migrate_leads(session, mdb, dry_run))
        all_counts.update(await migrate_campaigns(session, mdb, dry_run))
        all_counts.update(await migrate_agents(session, mdb, dry_run))
        all_counts.update(await migrate_messages(session, mdb, dry_run))
        all_counts.update(await migrate_activity(session, mdb, dry_run))
        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    mongo_client.close()

    mode = "DRY RUN (nothing written)" if dry_run else "APPLIED"
    print(f"\nMigration {mode}:")
    for key, value in all_counts.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Count what would migrate without writing")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
