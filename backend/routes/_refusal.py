"""Turn a refused send into an HTTP error, after recording the refusal durably.

`get_db_session` rolls the transaction back when an HTTPException propagates, so the audit entry is committed first.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from repositories import audit_repo
from services.send_gate import SendBlocked

STATUS_FOR_CODE = {
    "kill_switch": 423,
    "paused": 423,
    "limit_daily": 429,
    "limit_hourly": 429,
    "limit_delay": 429,
    "live_not_available": 501,
    "not_compliant": 422,
    "sender_not_configured": 409,
}


def block_detail(blocked: SendBlocked) -> dict:
    return {
        "code": blocked.code,
        "message": blocked.message,
        "retry_at": blocked.retry_at.isoformat() if blocked.retry_at else None,
    }


async def refusal(
    session: AsyncSession,
    user: dict,
    blocked: SendBlocked,
    *,
    resource_type: str = "outbound_message",
    resource_id: Optional[uuid.UUID] = None,
    action: str = "dispatch.blocked",
    channel: Optional[str] = None,
) -> HTTPException:
    await audit_repo.log(
        session,
        uuid.UUID(user["org_id"]),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_user_id=uuid.UUID(user["id"]),
        diff={
            "code": blocked.code,
            "retry_at": block_detail(blocked)["retry_at"],
            **({"channel": channel} if channel else {}),
        },
    )
    await session.commit()
    headers = {}
    if blocked.retry_at:
        headers["Retry-After"] = str(max(1, int((blocked.retry_at - datetime.now(timezone.utc)).total_seconds())))
    return HTTPException(
        status_code=STATUS_FOR_CODE.get(blocked.code, 409), detail=block_detail(blocked), headers=headers or None
    )
