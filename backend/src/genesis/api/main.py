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
from genesis.api.routes import (
    ask,
    automation,
    calendar,
    campaigns,
    customers,
    insights,
    invoices,
    jobs,
    leads,
    voice,
)
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
app.include_router(voice.router)
app.include_router(invoices.router)
app.include_router(leads.router)
app.include_router(ask.router)
app.include_router(calendar.router)
app.include_router(insights.router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, object]:
    """Connection state and configuration, for the Settings page and the
    sidebar indicator. Deliberately reports what is *not* configured too —
    a demo failing because of a missing value should say so, not go quiet."""
    db = await pool.healthcheck()
    return {
        "status": "ok",
        "database": db,
        "telegram_configured": settings.telegram_enabled,
        "ai_configured": settings.ai_enabled,
        "timezone": settings.business_timezone,
        "livekit_url": settings.livekit_url,
        "models": {
            "voice": "gpt-realtime",
            "reasoning": settings.reasoning_model,
        },
        "rates_usd_per_million": {
            "reasoning_input": settings.rate_mini_input,
            "reasoning_output": settings.rate_mini_output,
            "realtime_audio_input": settings.rate_realtime_audio_input,
            "realtime_audio_output": settings.rate_realtime_audio_output,
        },
        "policy": {
            "slot_hold_seconds": settings.slot_hold_ttl_seconds,
            "min_booking_lead_minutes": settings.min_booking_lead_minutes,
            "followup_delay_hours": settings.followup_delay_hours,
            "review_delay_hours": settings.review_delay_hours,
            "invoice_due_days": settings.invoice_due_days,
            "marketing_cooldown_days": settings.marketing_cooldown_days,
            "quiet_hours": f"{settings.quiet_hours_start}:00–{settings.quiet_hours_end}:00",
        },
    }
