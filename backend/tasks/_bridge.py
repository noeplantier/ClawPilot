"""Runs an async DB-touching function from a synchronous Celery task.

Celery's default (prefork) worker pool executes tasks one at a time per
process, but each task invocation here spins up a *new* asyncio event loop via
`asyncio.run()`. The app's request-path engine (db/session.py) pools asyncpg
connections that are bound to whichever loop created them, so reusing that
same pooled engine across separate `asyncio.run()` calls reliably breaks with
"attached to a different loop" errors. This module keeps a second engine,
built with NullPool (a fresh connection per use, nothing held across calls),
strictly for the Celery worker process.
"""

from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

_T = TypeVar("_T")

_engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool, future=True)
_SessionLocal = async_sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)


async def _run(fn: Callable[[AsyncSession], Awaitable[_T]]) -> _T:
    async with _SessionLocal() as session:
        try:
            result = await fn(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


def run_async(fn: Callable[[AsyncSession], Awaitable[_T]]) -> _T:
    """Call from a Celery task: `run_async(lambda session: my_async_fn(session, ...))`."""
    return asyncio.run(_run(fn))
