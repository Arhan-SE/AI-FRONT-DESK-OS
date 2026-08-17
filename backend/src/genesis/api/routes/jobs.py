"""Job pipeline endpoints.

Thin wrappers. All the rules live in genesis.domain.pipeline so the voice agent
and the automation worker enforce exactly the same ones without going through
HTTP.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from genesis.db import pool
from genesis.domain import pipeline
from genesis.settings import settings

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class CreateJobRequest(BaseModel):
    customer_id: str
    service_id: str
    technician_id: str
    starts_at: datetime
    notes: str | None = None
    # Lets a retried submit return the existing job instead of a duplicate.
    idempotency_key: str | None = None


class TransitionRequest(BaseModel):
    action: pipeline.Action


class JobResponse(BaseModel):
    id: str
    stage: str
    customer_name: str
    service_name: str
    technician_name: str
    starts_at: datetime
    customer_reachable: bool
    invoice_number: str | None = None
    invoice_amount: float | None = None
    due_on: str | None = None


class TransitionResponse(BaseModel):
    job_id: str
    action: str
    stage: str
    enqueued: list[str] = Field(default_factory=list)
    cancelled_jobs: int = 0


@router.get("", response_model=list[JobResponse])
async def list_jobs(limit: int = 100) -> list[JobResponse]:
    rows = await pool.fetch(
        """
        select id, stage, customer_name, service_name, technician_name,
               starts_at, customer_reachable, invoice_number, invoice_amount, due_on
          from v_jobs
         where business_id = $1
         order by starts_at desc
         limit $2
        """,
        settings.demo_business_id,
        limit,
    )
    return [
        JobResponse(
            id=str(r["id"]),
            stage=r["stage"],
            customer_name=r["customer_name"],
            service_name=r["service_name"],
            technician_name=r["technician_name"],
            starts_at=r["starts_at"],
            customer_reachable=r["customer_reachable"],
            invoice_number=r["invoice_number"],
            invoice_amount=float(r["invoice_amount"]) if r["invoice_amount"] else None,
            due_on=str(r["due_on"]) if r["due_on"] else None,
        )
        for r in rows
    ]


@router.post("", response_model=TransitionResponse, status_code=201)
async def create_job(body: CreateJobRequest) -> TransitionResponse:
    job_id = await pipeline.create_job(
        customer_id=body.customer_id,
        service_id=body.service_id,
        technician_id=body.technician_id,
        starts_at=body.starts_at,
        source="manual",
        notes=body.notes,
        idempotency_key=body.idempotency_key,
    )
    return TransitionResponse(job_id=job_id, action="create", stage="scheduled")


@router.post("/{job_id}/transition", response_model=TransitionResponse)
async def transition_job(job_id: str, body: TransitionRequest) -> TransitionResponse:
    result = await pipeline.transition(job_id, body.action)
    return TransitionResponse(
        job_id=result.job_id,
        action=result.action.value,
        stage=result.stage,
        enqueued=result.enqueued,
        cancelled_jobs=result.cancelled_jobs,
    )


class OptionsResponse(BaseModel):
    customers: list[dict]
    services: list[dict]
    technicians: list[dict]


@router.get("/options", response_model=OptionsResponse)
async def job_options() -> OptionsResponse:
    """Everything the 'new job' form needs, in one round trip."""
    async with pool.connection() as conn:
        customers = await conn.fetch(
            """select id, full_name, phone, telegram_chat_id is not null as reachable
                 from customers where business_id = $1 order by full_name""",
            settings.demo_business_id,
        )
        services = await conn.fetch(
            """select id, name, duration_minutes, base_price
                 from services where business_id = $1 and is_active
                 order by name""",
            settings.demo_business_id,
        )
        technicians = await conn.fetch(
            """select id, full_name from technicians
                where business_id = $1 and is_active order by full_name""",
            settings.demo_business_id,
        )

    return OptionsResponse(
        customers=[
            {
                "id": str(c["id"]),
                "name": c["full_name"],
                "phone": c["phone"],
                "reachable": c["reachable"],
            }
            for c in customers
        ],
        services=[
            {
                "id": str(s["id"]),
                "name": s["name"],
                "duration_minutes": s["duration_minutes"],
                "price": float(s["base_price"]),
            }
            for s in services
        ],
        technicians=[{"id": str(t["id"]), "name": t["full_name"]} for t in technicians],
    )
