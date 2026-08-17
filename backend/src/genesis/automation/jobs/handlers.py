"""One handler per automation job type.

Handlers load the context a template needs and hand it to
send_customer_message. They never touch Telegram directly, so the Communication
Guard is unavoidable — its frequency caps and duplicate prevention are
guarantees rather than conventions.

A handler returning normally means "this job is done". Raising means "retry".
A Guard block is *not* an error: the system did exactly what it should, so the
job succeeds and the refusal is recorded.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from genesis.db import pool
from genesis.domain.communication.messenger import send_customer_message
from genesis.domain.communication.types import MessageType, SendResult
from genesis.settings import settings

log = logging.getLogger(__name__)


def _local(dt: datetime) -> datetime:
    return dt.astimezone(settings.tz)


def _when(dt: datetime) -> str:
    return _local(dt).strftime("%A %d %b at %I:%M %p").replace(" 0", " ")


def _time(dt: datetime) -> str:
    return _local(dt).strftime("%I:%M %p").lstrip("0")


def _date(dt: datetime) -> str:
    return _local(dt).strftime("%d %b")


async def _appointment_context(appointment_id: str) -> dict[str, Any] | None:
    return await pool.fetchrow(
        """
        select a.id, a.starts_at, a.status, a.customer_id,
               c.full_name as customer_name,
               s.name as service_name,
               t.full_name as technician_name
          from appointments a
          join customers   c on c.id = a.customer_id
          join services    s on s.id = a.service_id
          join technicians t on t.id = a.technician_id
         where a.id = $1 and a.business_id = $2
        """,
        appointment_id,
        settings.demo_business_id,
    )


# ---------------------------------------------------------------- handlers


async def appointment_confirmation(payload: dict) -> SendResult:
    appt = await _appointment_context(payload["appointment_id"])
    if appt is None:
        raise ValueError("Appointment no longer exists")

    return await send_customer_message(
        business_id=settings.demo_business_id,
        customer_id=str(appt["customer_id"]),
        message_type=MessageType.APPOINTMENT_CONFIRMATION,
        context={
            "name": appt["customer_name"].split()[0],
            "service": appt["service_name"],
            "when": _when(appt["starts_at"]),
            "technician": appt["technician_name"],
        },
        dedupe_key=str(appt["id"]),
    )


async def appointment_reminder(payload: dict) -> SendResult:
    appt = await _appointment_context(payload["appointment_id"])
    if appt is None:
        raise ValueError("Appointment no longer exists")

    # Defence in depth: the pipeline cancels this job on completion or
    # cancellation, but the worker must not send one if that ever slips.
    if appt["status"] not in ("booked", "confirmed"):
        log.info("skipping reminder for %s job", appt["status"])
        return SendResult(sent=False, blocked=True, code=None, reason="Job no longer upcoming")

    return await send_customer_message(
        business_id=settings.demo_business_id,
        customer_id=str(appt["customer_id"]),
        message_type=MessageType.APPOINTMENT_REMINDER,
        context={"service": appt["service_name"], "time": _time(appt["starts_at"])},
        dedupe_key=str(appt["id"]),
    )


async def post_service_followup(payload: dict) -> SendResult:
    appt = await _appointment_context(payload["appointment_id"])
    if appt is None:
        raise ValueError("Appointment no longer exists")

    return await send_customer_message(
        business_id=settings.demo_business_id,
        customer_id=str(appt["customer_id"]),
        message_type=MessageType.POST_SERVICE_FOLLOWUP,
        context={
            "name": appt["customer_name"].split()[0],
            "service": appt["service_name"],
            "date": _date(appt["starts_at"]),
        },
        dedupe_key=str(appt["id"]),
    )


async def review_request(payload: dict) -> SendResult:
    appt = await _appointment_context(payload["appointment_id"])
    if appt is None:
        raise ValueError("Appointment no longer exists")

    result = await send_customer_message(
        business_id=settings.demo_business_id,
        customer_id=str(appt["customer_id"]),
        message_type=MessageType.REVIEW_REQUEST,
        context={
            "name": appt["customer_name"].split()[0],
            "service": appt["service_name"],
        },
        dedupe_key=str(appt["id"]),
    )

    # Record the ask so the Reviews page can show response rate honestly —
    # requested versus actually answered.
    if result.sent:
        await pool.execute(
            """
            insert into reviews (business_id, customer_id, appointment_id, source, requested_at)
            values ($1, $2, $3, 'telegram', now())
            on conflict (appointment_id) do nothing
            """,
            settings.demo_business_id,
            appt["customer_id"],
            appt["id"],
        )
    return result


async def payment_reminder(payload: dict) -> SendResult:
    invoice_id = payload["invoice_id"]
    attempt = int(payload.get("attempt", 1))

    invoice = await pool.fetchrow(
        """
        select i.id, i.invoice_number, i.amount, i.due_on, i.status, i.customer_id,
               c.full_name as customer_name
          from invoices i
          join customers c on c.id = i.customer_id
         where i.id = $1 and i.business_id = $2
        """,
        invoice_id,
        settings.demo_business_id,
    )
    if invoice is None:
        raise ValueError("Invoice no longer exists")

    # Never chase a settled invoice. The pipeline cancels these on payment, but
    # a race between "mark paid" and the worker claiming this job is possible.
    if invoice["status"] in ("paid", "void"):
        return SendResult(sent=False, blocked=True, code=None, reason="Invoice already settled")

    # Mark overdue once the due date has passed, so the board reflects reality.
    if invoice["due_on"] < datetime.now(UTC).date() and invoice["status"] != "overdue":
        await pool.execute("update invoices set status = 'overdue' where id = $1", invoice_id)

    result = await send_customer_message(
        business_id=settings.demo_business_id,
        customer_id=str(invoice["customer_id"]),
        message_type=MessageType.PAYMENT_REMINDER,
        context={
            "name": invoice["customer_name"].split()[0],
            "invoice": invoice["invoice_number"],
            "amount": f"{invoice['amount']:,.0f}",
            "due": invoice["due_on"].strftime("%d %b"),
        },
        # Each attempt is its own message, so escalating reminders are allowed
        # while a retry of the same attempt is not.
        dedupe_key=f"{invoice_id}:{attempt}",
    )

    # Schedule the next chase, up to the cap. Paying cancels the chain.
    if result.sent and attempt < settings.max_payment_reminders:
        await pool.execute(
            """
            insert into automation_jobs
              (business_id, job_type, scheduled_for, payload, dedupe_key)
            values ($1, 'payment_reminder', $2, $3::jsonb, $4)
            on conflict do nothing
            """,
            settings.demo_business_id,
            datetime.now(UTC) + timedelta(days=settings.payment_reminder_repeat_days),
            f'{{"invoice_id": "{invoice_id}", "attempt": {attempt + 1}}}',
            f"invoice:{invoice_id}:reminder:{attempt + 1}",
        )

    return result


HANDLERS = {
    "appointment_confirmation": appointment_confirmation,
    "appointment_reminder": appointment_reminder,
    "post_service_followup": post_service_followup,
    "review_request": review_request,
    "payment_reminder": payment_reminder,
}
