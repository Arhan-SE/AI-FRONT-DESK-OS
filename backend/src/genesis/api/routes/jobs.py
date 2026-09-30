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
from genesis.domain.observability import decisions
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
    invoice_id: str | None = None
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
               starts_at, customer_reachable, invoice_id, invoice_number,
               invoice_amount, due_on
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
            invoice_id=str(r["invoice_id"]) if r["invoice_id"] else None,
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


@router.delete("/{job_id}")
async def delete_job(job_id: str) -> dict:
    """Remove a job entirely, with its invoice and queued work.

    Distinct from cancelling: cancelling records that a booking was called off,
    deleting says it should never have been recorded. Only the second frees the
    technician's slot in a way that leaves no trace.
    """
    async with pool.transaction() as conn:
        row = await conn.fetchrow(
            """select a.id, c.full_name, s.name as service
                 from appointments a
                 join customers c on c.id = a.customer_id
                 join services  s on s.id = a.service_id
                where a.id = $1 and a.business_id = $2""",
            job_id,
            settings.demo_business_id,
        )
        if row is None:
            raise ValueError("Job not found")

        cancelled = await conn.fetchval(
            """
            with c as (
              update automation_jobs set status = 'cancelled', completed_at = now()
               where business_id = $1 and status = 'pending' and dedupe_key like $2
              returning 1
            ) select count(*) from c
            """,
            settings.demo_business_id,
            f"appointment:{job_id}:%",
        )
        # invoices.appointment_id is ON DELETE SET NULL, so the paperwork would
        # otherwise survive its job as an orphan.
        await conn.execute(
            """delete from payments where invoice_id in
                 (select id from invoices where appointment_id = $1)""",
            job_id,
        )
        await conn.execute("delete from invoices where appointment_id = $1", job_id)
        await conn.execute("delete from appointments where id = $1", job_id)

        await decisions.record(
            business_id=settings.demo_business_id,
            event_type="job_deleted",
            status="pending",
            summary=f"Job deleted — {row['service']} for {row['full_name']}",
            detail={"cancelled_jobs": int(cancelled or 0)},
            conn=conn,
        )

    return {"deleted": job_id, "cancelled_jobs": int(cancelled or 0)}


class CorrectionRequest(BaseModel):
    stage: pipeline.Stage


@router.post("/{job_id}/correct", response_model=TransitionResponse)
async def correct_job(job_id: str, body: CorrectionRequest) -> TransitionResponse:
    """Fix a stage set by mistake, undoing what it set in motion.

    Separate from /transition on purpose: a transition records what happened,
    a correction records that the record was wrong.
    """
    result = await pipeline.correct_stage(job_id, body.stage)
    return TransitionResponse(
        job_id=result.job_id,
        action="correct",
        stage=result.stage,
        enqueued=result.enqueued,
        cancelled_jobs=result.cancelled_jobs,
    )


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
