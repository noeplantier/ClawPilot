"""Activity feed on top of the append-only `audit_logs` table.

Replaces the former Mongo `activity` collection. A feed entry is an audit row:
`action` carries the dotted kind (e.g. "lead.created"), `diff` carries the
human title and free-form meta. The JSON shape returned by `list_recent` is
unchanged from the Mongo days (`id`, `org_id`, `kind`, `title`, `meta`, `created_at`).
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog
from repositories import audit_repo


async def record(
    session: AsyncSession,
    org_id: str | uuid.UUID,
    kind: str,
    title: str,
    meta: Optional[dict] = None,
) -> None:
    await audit_repo.log(
        session,
        uuid.UUID(str(org_id)),
        action=kind,
        resource_type=kind.split(".", 1)[0],
        diff={"title": title, "meta": meta or {}},
    )


async def list_recent(session: AsyncSession, org_id: str | uuid.UUID, limit: int = 30) -> list[dict]:
    account_id = uuid.UUID(str(org_id))
    rows = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.account_id == account_id)
            .order_by(AuditLog.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
    ).scalars()
    out = []
    for r in rows:
        diff = r.diff or {}
        out.append(
            {
                "id": str(r.id),
                "org_id": str(r.account_id),
                "kind": r.action,
                "title": diff.get("title", r.action),
                "meta": diff.get("meta", {}),
                "created_at": r.created_at.isoformat(),
            }
        )
    return out
