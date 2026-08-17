"""Automation queue endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from genesis.automation import worker
from genesis.db import pool
from genesis.settings import settings

router = APIRouter(prefix="/api/automation", tags=["automation"])


class QueueItem(BaseModel):
    id: str
    job_type: str
    status: str
    scheduled_for: datetime
    attempts: int
    last_error: str | None = None


class RunNowResponse(BaseModel):
    advanced: int
    executed: int


@router.get("/queue", response_model=list[QueueItem])
async def queue(limit: int = 50) -> list[QueueItem]:
    rows = await pool.fetch(
        """
        select id, job_type, status, scheduled_for, attempts, last_error
          from automation_jobs
         where business_id = $1
         order by scheduled_for desc
         limit $2
        """,
        settings.demo_business_id,
        limit,
    )
    return [
        QueueItem(
            id=str(r["id"]),
            job_type=r["job_type"],
            status=r["status"],
            scheduled_for=r["scheduled_for"],
            attempts=r["attempts"],
            last_error=r["last_error"],
        )
        for r in rows
    ]


@router.post("/run-due", response_model=RunNowResponse)
async def run_due() -> RunNowResponse:
    """Pull every pending job forward and execute it immediately.

    Real delays are 2h and 24h, which a demo cannot wait for. This advances the
    clock — it does not shorten or bypass anything. The same handlers run, the
    same Guard applies, and a job the Guard would block is still blocked.
    """
    advanced = int(
        await pool.fetchval(
            """
            with moved as (
              update automation_jobs
                 set scheduled_for = now()
               where business_id = $1 and status = 'pending' and scheduled_for > now()
              returning 1
            )
            select count(*) from moved
            """,
            settings.demo_business_id,
        )
        or 0
    )
    executed = await worker.drain_once()
    return RunNowResponse(advanced=advanced, executed=executed)
