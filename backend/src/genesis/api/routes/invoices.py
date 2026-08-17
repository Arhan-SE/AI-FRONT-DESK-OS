"""Invoice endpoints.

Editing an invoice is not the same as moving a job through the pipeline, so it
lives here rather than behind a transition. Changing an amount or a due date is
a correction to a record; marking one paid is an event.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from genesis.db import pool
from genesis.domain.observability import decisions
from genesis.settings import settings

router = APIRouter(prefix="/api/invoices", tags=["invoices"])

EDITABLE = {"amount", "due_on", "status", "invoice_number"}


class InvoiceUpdate(BaseModel):
    amount: float | None = Field(default=None, ge=0)
    due_on: date | None = None
    status: str | None = None
    invoice_number: str | None = Field(default=None, min_length=1, max_length=40)


@router.patch("/{invoice_id}")
async def update_invoice(invoice_id: str, body: InvoiceUpdate) -> dict:
    changes = {
        k: v for k, v in body.model_dump(exclude_unset=True).items() if k in EDITABLE
    }
    if not changes:
        raise ValueError("Nothing to update")

    if changes.get("status") not in (None, "draft", "sent", "paid", "overdue", "void"):
        raise ValueError("status must be draft, sent, paid, overdue or void")

    async with pool.transaction() as conn:
        existing = await conn.fetchrow(
            "select id, status, invoice_number from invoices where id = $1 and business_id = $2",
            invoice_id,
            settings.demo_business_id,
        )
        if existing is None:
            raise ValueError("Invoice not found")

        # Marking paid here must do what the pipeline does, or the two paths
        # would leave the database in different shapes for the same outcome.
        if changes.get("status") == "paid" and existing["status"] != "paid":
            changes["paid_at"] = "now()"

        columns = [c for c in changes if c != "paid_at"]
        assignments = ", ".join(f"{c} = ${i + 3}" for i, c in enumerate(columns))
        if changes.get("paid_at"):
            assignments += ", paid_at = now()"
        elif changes.get("status") in ("sent", "overdue", "draft"):
            assignments += ", paid_at = null"

        await conn.execute(
            f"update invoices set {assignments} where id = $1 and business_id = $2",  # noqa: S608
            invoice_id,
            settings.demo_business_id,
            *[changes[c] for c in columns],
        )

        if changes.get("status") == "paid":
            await conn.execute(
                """
                insert into payments (business_id, invoice_id, amount, method)
                select business_id, id, amount, 'cash' from invoices where id = $1
                """,
                invoice_id,
            )
            await conn.execute(
                """update automation_jobs set status = 'cancelled', completed_at = now()
                    where business_id = $1 and status = 'pending'
                      and dedupe_key like $2""",
                settings.demo_business_id,
                f"invoice:{invoice_id}:%",
            )
        elif changes.get("status") in ("sent", "overdue", "draft", "void"):
            await conn.execute("delete from payments where invoice_id = $1", invoice_id)

        await decisions.record(
            business_id=settings.demo_business_id,
            event_type="invoice_updated",
            summary=f"Invoice {existing['invoice_number']} edited — {', '.join(columns)}",
            detail={"fields": columns},
            conn=conn,
        )

    return {"id": invoice_id, "updated": columns}


@router.delete("/{invoice_id}", status_code=200)
async def delete_invoice(invoice_id: str) -> dict:
    """Remove an invoice entirely, along with its payments and pending chases.

    The job it came from stays — deleting the paperwork does not undo the work.
    """
    async with pool.transaction() as conn:
        existing = await conn.fetchrow(
            "select invoice_number from invoices where id = $1 and business_id = $2",
            invoice_id,
            settings.demo_business_id,
        )
        if existing is None:
            raise ValueError("Invoice not found")

        await conn.execute("delete from payments where invoice_id = $1", invoice_id)
        cancelled = await conn.fetchval(
            """
            with c as (
              update automation_jobs set status = 'cancelled', completed_at = now()
               where business_id = $1 and status = 'pending' and dedupe_key like $2
              returning 1
            ) select count(*) from c
            """,
            settings.demo_business_id,
            f"invoice:{invoice_id}:%",
        )
        await conn.execute("delete from invoices where id = $1", invoice_id)

        await decisions.record(
            business_id=settings.demo_business_id,
            event_type="invoice_deleted",
            status="pending",
            summary=f"Invoice {existing['invoice_number']} deleted",
            detail={"cancelled_reminders": int(cancelled or 0)},
            conn=conn,
        )

    return {"deleted": invoice_id, "cancelled_reminders": int(cancelled or 0)}
