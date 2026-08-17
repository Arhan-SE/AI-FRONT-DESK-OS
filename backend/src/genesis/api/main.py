"""FastAPI application — the write path.

The browser reads directly from Supabase under RLS. Everything that changes
state comes through here, where business rules, validation and the audit trail
are enforced.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from genesis.api.errors import register_error_handlers
from genesis.api.routes import automation, campaigns, customers, jobs
from genesis.db import pool
from genesis.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("genesis.api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await pool.init_pool()
    health = await pool.healthcheck()
    log.info(
        "ready — postgres %s, %s customers, %s appointments",
        health["postgres"],
        health["customers"],
        health["appointments"],
    )
    if not settings.telegram_enabled:
        log.warning("TELEGRAM_BOT_TOKEN not set — outreach will be blocked by the Guard")
    yield
    await pool.close_pool()


app = FastAPI(
    title="Genesis OS",
    description="AI Business Operating System",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(jobs.router)
app.include_router(automation.router)
app.include_router(campaigns.router)
app.include_router(customers.router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, object]:
    """Used by the frontend to show a connection state rather than hanging."""
    db = await pool.healthcheck()
    return {
        "status": "ok",
        "database": db,
        "telegram_configured": settings.telegram_enabled,
        "ai_configured": settings.ai_enabled,
        "timezone": settings.business_timezone,
    }
