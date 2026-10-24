"""Seed demo data for a new organization."""

import random
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Agent as AgentORM
from repositories import campaign_repo, lead_repo


async def seed_demo_data(session: AsyncSession, org_id: str) -> None:
    account_id = uuid.UUID(org_id)

    # Avoid double-seeding
    existing = await lead_repo.count_leads(session, account_id)
    if existing > 0:
        return

    # ---- Agents (Postgres — see repositories/agent_repo.py) ----
    agents = [
        AgentORM(
            account_id=account_id,
            name="Atlas",
            role="outreach",
            status="running",
            tasks_completed=482,
            tasks_in_queue=12,
        ),
        AgentORM(
            account_id=account_id,
            name="Nyx",
            role="enrichment",
            status="running",
            tasks_completed=1204,
            tasks_in_queue=3,
        ),
        AgentORM(
            account_id=account_id, name="Orion", role="scraper", status="idle", tasks_completed=87, tasks_in_queue=0
        ),
        AgentORM(
            account_id=account_id, name="Vega", role="responder", status="paused", tasks_completed=55, tasks_in_queue=7
        ),
    ]
    session.add_all(agents)
    await session.flush()

    # ---- Leads (Postgres — see repositories/lead_repo.py) ----
    names = [
        ("Priya Shah", "priya.shah@acme.io", "Acme Labs", "VP Growth", "IN", "en"),
        ("Lucas Moreau", "lucas@vivelab.fr", "ViveLab", "CEO", "FR", "fr"),
        ("Hana Kobayashi", "hana@kaze.jp", "Kaze Technologies", "Head of Sales", "JP", "ja"),
        ("Sofia Reyes", "sofia@ventura.mx", "Ventura Cloud", "Founder", "MX", "es"),
        ("Marcus Kent", "marcus@northfold.com", "Northfold", "Director of RevOps", "US", "en"),
        ("Amira Haddad", "amira@zayd.ae", "Zayd Digital", "Marketing Lead", "AE", "ar"),
        ("Tobias Lang", "tobias@kern.de", "Kern GmbH", "CTO", "DE", "de"),
        ("Elena Romano", "elena@agora.it", "Agora Srl", "COO", "IT", "it"),
        ("Wei Chen", "wei@linke.cn", "Linke", "Partnerships", "CN", "zh"),
        ("Oluchi Obi", "oluchi@zest.ng", "Zest Africa", "Founder", "NG", "en"),
        ("Rafael Costa", "rafael@orbita.br", "Orbita", "Head of BD", "BR", "pt"),
        ("Nora Lindqvist", "nora@flux.se", "Flux AB", "CMO", "SE", "en"),
    ]
    stages = ["new", "new", "contacted", "engaged", "qualified", "won"]
    lead_ids: list[str] = []
    for nm, em, co, ti, cc, lg in names:
        lead, _ = await lead_repo.create_lead(
            session,
            account_id,
            {
                "full_name": nm,
                "email": em,
                "phone": f"+1415555{random.randint(1000, 9999)}",
                "company": co,
                "title": ti,
                "country": cc,
                "language": lg,
                "stage": random.choice(stages),
                "tags": random.sample(["saas", "fintech", "b2b", "smb", "enterprise", "growth"], k=2),
                "source": random.choice(["linkedin", "webinar", "referral", "inbound"]),
                "notes": None,
                # score is computed automatically at creation time (see
                # repositories/lead_repo.py::rescore_lead) — no need to seed one.
                # Demo data only (not real prospects) — pre-granting consent so
                # the seeded campaigns can actually demonstrate sending.
                "email_opt_in": True,
                "whatsapp_opt_in": True,
                "consent_source": "demo_seed",
            },
        )
        lead_ids.append(str(lead.id))

    # ---- Campaigns (Postgres — see repositories/campaign_repo.py) ----
    steps_a = [
        {
            "channel": "email",
            "delay_hours": 0,
            "subject": "Quick question about {{company}}",
            "body": "Hi {{first_name}}, ...",
            "language": "en",
        },
        {
            "channel": "whatsapp",
            "delay_hours": 48,
            "body": "Hey {{first_name}}, just bumping my last email — worth a quick chat?",
            "language": "en",
        },
        {
            "channel": "email",
            "delay_hours": 120,
            "subject": "Closing the loop",
            "body": "Last note from my side...",
            "language": "en",
        },
    ]
    for name, goal, status, sent, opened, replied, converted in [
        ("APAC SaaS Founders Q1", "Book 25 discovery calls", "running", 482, 312, 41, 11),
        ("EU Enterprise Outreach", "Pipeline generation for Q2", "running", 189, 140, 22, 4),
        ("Agency Partnership Drive", "Recruit 10 partners", "paused", 67, 44, 6, 1),
        ("North America Reactivation", "Win back churned accounts", "draft", 0, 0, 0, 0),
    ]:
        await campaign_repo.create_campaign(
            session,
            account_id,
            {
                "name": name,
                "goal": goal,
                "status": status,
                "channels": ["email", "whatsapp"],
                "steps": steps_a,
                "lead_ids": lead_ids if status != "draft" else [],
                "agent_id": None,
                "sent": sent,
                "opened": opened,
                "replied": replied,
                "converted": converted,
            },
        )
