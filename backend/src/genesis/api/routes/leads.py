"""Lead endpoints.

Leads normally arrive from the voice agent, which scores them. These exist so
one can be entered or corrected by hand — a lead that came in by word of mouth
is still a lead.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from genesis.db import pool
from genesis.domain.leads import scoring
from genesis.domain.observability import decisions
from genesis.settings import settings

router = APIRouter(prefix="/api/leads", tags=["leads"])

STATUSES = {"new", "qualified", "contacted", "converted", "lost"}
URGENCIES = {"low", "medium", "high"}


class LeadCreate(BaseModel):
    customer_id: str | None = None
    service_id: str | None = None
    location: str | None = None
    urgency: str | None = None
    preferred_timing: str | None = None
    notes: str | None = None

    @field_validator("urgency")
    @classmethod
    def _urgency(cls, v: str | None) -> str | None:
        if v and v not in URGENCIES:
            raise ValueError("urgency must be low, medium or high")
        return v


class LeadUpdate(BaseModel):
    status: str | None = None
    urgency: str | None = None
    location: str | None = None
    preferred_timing: str | None = None
    next_action: str | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def _status(cls, v: str | None) -> str | None:
        if v and v not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(sorted(STATUSES))}")
        return v


@router.post("", status_code=201)
async def create_lead(body: LeadCreate) -> dict:
    service_name = None
    if body.service_id:
        service_name = await pool.fetchval(
            "select name from services where id = $1 and business_id = $2",
            body.service_id,
            settings.demo_business_id,
        )

    # Scored through the same path the voice agent uses, so a hand-entered lead
    # is comparable with a captured one rather than sitting unscored.
    lead_id, score = await scoring.upsert_lead(
        conversation_id=None,
        customer_id=body.customer_id,
        service_id=body.service_id,
        service_name=service_name,
        location=body.location,
        urgency=body.urgency,
        preferred_timing=body.preferred_timing,
    )

    if body.notes:
        await pool.execute(
            "update leads set notes = $2, source = 'manual' where id = $1",
            lead_id,
            body.notes,
        )
    else:
        await pool.execute("update leads set source = 'manual' where id = $1", lead_id)

    return {
        "id": lead_id,
        "score": score.score,
        "classification": score.classification,
    }


@router.patch("/{lead_id}")
async def update_lead(lead_id: str, body: LeadUpdate) -> dict:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise ValueError("Nothing to update")

    columns = list(changes)
    assignments = ", ".join(f"{c} = ${i + 3}" for i, c in enumerate(columns))
    row = await pool.fetchrow(
        f"""update leads set {assignments}
             where id = $1 and business_id = $2
            returning id, status""",  # noqa: S608 — columns come from the model
        lead_id,
        settings.demo_business_id,
        *[changes[c] for c in columns],
    )
    if row is None:
        raise ValueError("Lead not found")

    await decisions.record(
        business_id=settings.demo_business_id,
        event_type="lead_updated",
        summary=f"Lead updated — {', '.join(columns)}",
        detail={"lead_id": lead_id, "fields": columns},
    )
    return {"id": lead_id, "status": row["status"]}


@router.delete("/{lead_id}")
async def delete_lead(lead_id: str) -> dict:
    deleted = await pool.fetchval(
        "delete from leads where id = $1 and business_id = $2 returning id",
        lead_id,
        settings.demo_business_id,
    )
    if deleted is None:
        raise ValueError("Lead not found")

    await decisions.record(
        business_id=settings.demo_business_id,
        event_type="lead_deleted",
        status="pending",
        summary="Lead deleted",
        detail={"lead_id": lead_id},
    )
    return {"deleted": lead_id}
