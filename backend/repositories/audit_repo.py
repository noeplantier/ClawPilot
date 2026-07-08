"""Append-only audit trail — used for compliance-sensitive decisions (blocked
sends, consent changes) where the legacy Mongo `activity` feed isn't durable/
queryable enough. See plan doc section 1.19.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog


async def log(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    action: str,
    resource_type: str,
    resource_id: Optional[uuid.UUID] = None,
    actor_type: str = "system",
    actor_user_id: Optional[uuid.UUID] = None,
    diff: Optional[dict] = None,
) -> AuditLog:
    entry = AuditLog(
        account_id=account_id,
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        diff=diff,
    )
    session.add(entry)
    await session.flush()
    return entry
