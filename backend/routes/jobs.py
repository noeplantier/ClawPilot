"""Account-scoped status for persisted Celery jobs."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import JobRun
from db.session import get_db_session
from deps import get_current_user
from models import JobRunOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobRunOut)
async def get_job_run(
    job_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    job = (
        await session.execute(select(JobRun).where(JobRun.id == job_id, JobRun.account_id == uuid.UUID(user["org_id"])))
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobRunOut(
        id=str(job.id),
        job_type=job.job_type,
        status=job.status,
        total_items=job.total_items,
        processed_items=job.processed_items,
        failed_items=job.failed_items,
        started_at=job.started_at,
        finished_at=job.finished_at,
        duration_ms=job.duration_ms,
        error=job.error,
        created_by=str(job.created_by) if job.created_by else None,
        created_at=job.created_at,
    )
