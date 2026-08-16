"""Shared asyncpg connection pool.

PostgREST cannot express what this system needs — transactions, SELECT ... FOR
UPDATE SKIP LOCKED for job claiming, catching exclusion-constraint violations by
SQLSTATE, and pgvector similarity search — so the backend talks to Postgres
directly and leaves the REST API to the browser's read path.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg

from genesis.settings import settings

log = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

# Raised by the appointments exclusion constraint and the hold overlap
# constraint. Callers translate this into a domain-level "slot taken".
EXCLUSION_VIOLATION = "23P01"
UNIQUE_VIOLATION = "23505"


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool

    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. It must be a postgresql:// connection "
            "string (Supabase → Connect → Session pooler), not the REST API URL."
        )

    _pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=1,
        max_size=8,
        # Supabase's pooler can hand back a reused session; disabling the
        # statement cache keeps asyncpg from assuming its prepared statements
        # survived. Cheap insurance against an intermittent, demo-day-only bug.
        statement_cache_size=0,
        command_timeout=30,
    )
    log.info("database pool ready")
    return _pool


async def get_pool() -> asyncpg.Pool:
    return _pool if _pool is not None else await init_pool()


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def connection() -> AsyncIterator[asyncpg.Connection]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def transaction() -> AsyncIterator[asyncpg.Connection]:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        yield conn


async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    async with connection() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args: Any) -> asyncpg.Record | None:
    async with connection() as conn:
        return await conn.fetchrow(query, *args)


async def fetchval(query: str, *args: Any) -> Any:
    async with connection() as conn:
        return await conn.fetchval(query, *args)


async def execute(query: str, *args: Any) -> str:
    async with connection() as conn:
        return await conn.execute(query, *args)


async def healthcheck() -> dict[str, Any]:
    """Used by `make dev-check` to catch a broken setup before a demo."""
    async with connection() as conn:
        return {
            "postgres": await conn.fetchval("show server_version"),
            "customers": await conn.fetchval(
                "select count(*) from customers where business_id = $1",
                settings.demo_business_id,
            ),
            "appointments": await conn.fetchval(
                "select count(*) from appointments where business_id = $1",
                settings.demo_business_id,
            ),
        }
