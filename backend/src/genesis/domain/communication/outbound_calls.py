"""Outbound calls — review requests, payment reminders, reactivation.

There is no telephony here and nothing goes out over Telegram: the "call" is
a LiveKit voice-agent session started directly from the dashboard, in the
same browser tab, briefed on why it's calling before anyone picks up. The
owner clicks a button on a job, invoice, or lead; the browser navigates to
/call/:purpose/:ref; that page asks the API to resolve `ref` into the facts
the agent needs.

Resolution re-derives everything from the database using the id in the URL
rather than trusting anything the browser could have sent — the same
discipline the booking tools already follow.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from genesis.db import pool
from genesis.settings import settings


class CallPurpose(StrEnum):
    REVIEW = "review"
    PAYMENT = "payment"
    REACTIVATION = "reactivation"


async def resolve_call_context(purpose: CallPurpose, ref: str) -> dict[str, Any] | None:
    """What the agent should know before anyone says a word.

    Returns None for a ref that does not exist or belongs to another
    business — the caller turns that into a 404 rather than starting a call
    the agent has nothing to say.
    """
    if purpose is CallPurpose.REVIEW:
        row = await pool.fetchrow(
            """
            select a.customer_id, c.full_name as customer_name,
                   s.name as service_name, a.starts_at
              from appointments a
              join customers c on c.id = a.customer_id
              join services  s on s.id = a.service_id
             where a.id = $1 and a.business_id = $2
            """,
            ref,
            settings.demo_business_id,
        )
        if row is None:
            return None
        return {
            "purpose": purpose.value,
            "customer_id": str(row["customer_id"]),
            "customer_name": row["customer_name"],
            "service": row["service_name"],
            "job_date": row["starts_at"].astimezone(settings.tz).strftime("%d %B"),
        }

    if purpose is CallPurpose.PAYMENT:
        row = await pool.fetchrow(
            """
            select i.customer_id, c.full_name as customer_name,
                   i.invoice_number, i.amount, i.due_on, i.status
              from invoices i
              join customers c on c.id = i.customer_id
             where i.id = $1 and i.business_id = $2
            """,
            ref,
            settings.demo_business_id,
        )
        if row is None:
            return None
        days_past_due = (datetime.now(UTC).date() - row["due_on"]).days
        return {
            "purpose": purpose.value,
            "customer_id": str(row["customer_id"]),
            "customer_name": row["customer_name"],
            "invoice_number": row["invoice_number"],
            "amount": f"{row['amount']:,.0f}",
            "days_past_due": max(0, days_past_due),
            "already_settled": row["status"] in ("paid", "void"),
        }

    row = await pool.fetchrow(
        """
        select c.id as customer_id, c.full_name as customer_name,
               (select s.name from appointments a
                  join services s on s.id = a.service_id
                 where a.customer_id = c.id and a.status = 'completed'
                 order by a.starts_at desc limit 1) as last_service,
               (select a.starts_at from appointments a
                 where a.customer_id = c.id and a.status = 'completed'
                 order by a.starts_at desc limit 1) as last_service_at
          from customers c
         where c.id = $1 and c.business_id = $2
        """,
        ref,
        settings.demo_business_id,
    )
    if row is None:
        return None
    months_since = None
    if row["last_service_at"]:
        months_since = max(1, int((datetime.now(UTC) - row["last_service_at"]).days / 30))
    return {
        "purpose": purpose.value,
        "customer_id": str(row["customer_id"]),
        "customer_name": row["customer_name"],
        "last_service": row["last_service"],
        "months_since": months_since,
    }
