"""Customer endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from genesis.db import pool
from genesis.domain.observability import decisions
from genesis.settings import settings

router = APIRouter(prefix="/api/customers", tags=["customers"])

# Only these may be written through the API. An allowlist rather than "whatever
# the client sent" — aggregates and timestamps are derived and must never be
# settable from outside.
EDITABLE = {
    "full_name",
    "phone",
    "email",
    "address",
    "telegram_chat_id",
    "telegram_opted_in",
    "do_not_contact",
    "status",
}


class CustomerUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    telegram_chat_id: int | None = None
    telegram_opted_in: bool | None = None
    do_not_contact: bool | None = None
    status: str | None = None

    @field_validator("status")
    @classmethod
    def _status(cls, v: str | None) -> str | None:
        if v is not None and v not in {"active", "dormant", "archived"}:
            raise ValueError("status must be active, dormant or archived")
        return v

    @field_validator("phone", "email", "address")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        return v.strip() or None if isinstance(v, str) else v


class CustomerCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    telegram_chat_id: int | None = None


@router.post("", status_code=201)
async def create_customer(body: CustomerCreate) -> dict:
    row = await pool.fetchrow(
        """
        insert into customers
          (business_id, full_name, phone, email, address, telegram_chat_id,
           telegram_opted_in, status)
        values ($1,$2,$3,$4,$5,$6,$7,'active')
        returning id, full_name
        """,
        settings.demo_business_id,
        body.full_name.strip(),
        body.phone,
        body.email,
        body.address,
        body.telegram_chat_id,
        body.telegram_chat_id is not None,
    )
    return {"id": str(row["id"]), "full_name": row["full_name"]}


@router.delete("/{customer_id}")
async def delete_customer(customer_id: str) -> dict:
    """Remove a customer and everything belonging to them.

    Reports what it removed rather than doing it silently — deleting a customer
    with jobs and invoices attached destroys more than the row you clicked.
    """
    async with pool.transaction() as conn:
        row = await conn.fetchrow(
            """
            select c.full_name,
                   (select count(*) from appointments a where a.customer_id = c.id) as jobs,
                   (select count(*) from invoices i where i.customer_id = c.id) as invoices
              from customers c
             where c.id = $1 and c.business_id = $2
            """,
            customer_id,
            settings.demo_business_id,
        )
        if row is None:
            raise ValueError("Customer not found")

        # Cancel queued work first: a message about a customer who no longer
        # exists would fail noisily in the worker for no reason.
        await conn.execute(
            """update automation_jobs set status = 'cancelled', completed_at = now()
                where business_id = $1 and status = 'pending'
                  and payload->>'appointment_id' in (
                    select id::text from appointments where customer_id = $2)""",
            settings.demo_business_id,
            customer_id,
        )
        await conn.execute("delete from customers where id = $1", customer_id)

        await decisions.record(
            business_id=settings.demo_business_id,
            event_type="customer_deleted",
            status="pending",
            summary=(
                f"{row['full_name']} deleted — {row['jobs']} job(s), "
                f"{row['invoices']} invoice(s)"
            ),
            detail={"jobs": row["jobs"], "invoices": row["invoices"]},
            conn=conn,
        )

    return {
        "deleted": customer_id,
        "name": row["full_name"],
        "jobs_removed": row["jobs"],
        "invoices_removed": row["invoices"],
    }


@router.patch("/{customer_id}")
async def update_customer(customer_id: str, body: CustomerUpdate) -> dict:
    changes = {
        k: v for k, v in body.model_dump(exclude_unset=True).items() if k in EDITABLE
    }
    if not changes:
        raise ValueError("Nothing to update")

    # Linking a chat id is what makes a customer reachable, so it implies
    # consent — otherwise the Guard would still refuse and the owner would be
    # left wondering why nothing sent after they pasted the id in.
    if changes.get("telegram_chat_id") is not None and "telegram_opted_in" not in changes:
        changes["telegram_opted_in"] = True
    if "telegram_chat_id" in changes and changes["telegram_chat_id"] is None:
        changes["telegram_opted_in"] = False

    columns = list(changes)
    assignments = ", ".join(f"{c} = ${i + 3}" for i, c in enumerate(columns))

    row = await pool.fetchrow(
        f"""
        update customers set {assignments}
         where id = $1 and business_id = $2
        returning id, full_name, telegram_chat_id
        """,  # noqa: S608 — column names come from the EDITABLE allowlist above
        customer_id,
        settings.demo_business_id,
        *[changes[c] for c in columns],
    )
    if row is None:
        raise ValueError("Customer not found")

    await decisions.record(
        business_id=settings.demo_business_id,
        customer_id=customer_id,
        event_type="customer_updated",
        summary=f"{row['full_name']} updated — {', '.join(columns)}",
        detail={"fields": columns},
    )
    return {
        "id": str(row["id"]),
        "full_name": row["full_name"],
        "reachable": row["telegram_chat_id"] is not None,
    }
