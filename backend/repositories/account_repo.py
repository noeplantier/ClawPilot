"""Account + User persistence — backs the auth route and `get_current_user`."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Account, User


async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: str) -> Optional[User]:
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return None
    result = await session.execute(select(User).where(User.id == uid))
    return result.scalar_one_or_none()


async def get_account(session: AsyncSession, account_id: str) -> Optional[Account]:
    try:
        aid = uuid.UUID(account_id)
    except ValueError:
        return None
    result = await session.execute(select(Account).where(Account.id == aid))
    return result.scalar_one_or_none()


async def list_all_account_ids(session: AsyncSession) -> list[uuid.UUID]:
    """Used by periodic automation jobs (rescore/reactivate/etc.) that run
    once per account — see tasks/automation_tasks.py."""
    result = await session.execute(select(Account.id))
    return list(result.scalars().all())


async def create_account_with_owner(
    session: AsyncSession, *, org_name: str, email: str, password_hash: str, full_name: str
) -> tuple[Account, User]:
    account = Account(name=org_name)
    session.add(account)
    await session.flush()  # populates account.id for the FK below

    user = User(
        account_id=account.id,
        email=email.lower(),
        password_hash=password_hash,
        full_name=full_name,
        role="owner",
    )
    session.add(user)
    await session.flush()  # populates user.id/created_at for the response
    return account, user
