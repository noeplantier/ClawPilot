"""Create (or reuse) the local demo account and fill it with sample data.

Idempotent: re-running neither duplicates the account nor the sample data.
Local development only — it refuses to run when APP_ENV=production.

    cd backend && python -m scripts.seed_demo
"""

from __future__ import annotations

import asyncio
import os
import sys

from db.session import AsyncSessionLocal
from deps import hash_password
from repositories import account_repo
from services.seed import seed_demo_data

DEMO_EMAIL = "demo@clawpilot.io"
DEMO_PASSWORD = "Demo12345!"  # public, local-only credential — never used outside dev
DEMO_ORG = "ClawPilot Demo"


async def main() -> None:
    if os.environ.get("APP_ENV", "").lower() == "production":
        sys.exit("seed_demo refuses to run with APP_ENV=production")

    async with AsyncSessionLocal() as session:
        user = await account_repo.get_user_by_email(session, DEMO_EMAIL)
        if user is None:
            account, user = await account_repo.create_account_with_owner(
                session,
                org_name=DEMO_ORG,
                email=DEMO_EMAIL,
                password_hash=hash_password(DEMO_PASSWORD),
                full_name="Demo Operator",
            )
            account_id = str(account.id)
            print(f"created demo account {DEMO_EMAIL}")
        else:
            account_id = str(user.account_id)
            print(f"demo account {DEMO_EMAIL} already exists")
        await seed_demo_data(session, account_id)  # no-op if the account already has leads
        await session.commit()
    print(f"login: {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
