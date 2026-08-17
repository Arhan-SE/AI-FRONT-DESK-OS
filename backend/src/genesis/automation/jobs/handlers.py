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


async def invoice_sent(payload: dict) -> SendResult:
    """Deliver the bill at the moment it is raised, not when it goes overdue."""
    invoice = await pool.fetchrow(
        """
        select i.id, i.invoice_number, i.amount, i.due_on, i.status, i.customer_id,
               c.full_name as customer_name, s.name as service_name
          from invoices i
          join customers c on c.id = i.customer_id
          left join appointments a on a.id = i.appointment_id
          left join services s on s.id = a.service_id
         where i.id = $1 and i.business_id = $2
        """,
        payload["invoice_id"],
        settings.demo_business_id,
    )
    if invoice is None:
        raise ValueError("Invoice no longer exists")

    if invoice["status"] in ("paid", "void"):
        return SendResult(sent=False, blocked=True, code=None, reason="Invoice already settled")

    return await send_customer_message(
        business_id=settings.demo_business_id,
        customer_id=str(invoice["customer_id"]),
        message_type=MessageType.INVOICE_SENT,
        context={
            "name": invoice["customer_name"].split()[0],
            "invoice": invoice["invoice_number"],
            "amount": f"{invoice['amount']:,.0f}",
            "due": invoice["due_on"].strftime("%d %b"),
            "service": invoice["service_name"] or "the work",
        },
        dedupe_key=str(invoice["id"]),
    )


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

    # Whether the due date has passed must be stated, not implied. Given only
    # "due: 24 Aug" the model will happily write "unpaid since 24 Aug" about a
    # date still in the future.
    days_past_due = (datetime.now(UTC).date() - invoice["due_on"]).days
    if days_past_due > 0:
        timing = f"overdue by {days_past_due} day(s)"
    elif days_past_due == 0:
        timing = "due today"
    else:
        timing = f"not yet due — payable in {-days_past_due} day(s)"

    result = await send_customer_message(
        business_id=settings.demo_business_id,
        customer_id=str(invoice["customer_id"]),
        message_type=MessageType.PAYMENT_REMINDER,
        context={
            "name": invoice["customer_name"].split()[0],
            "invoice": invoice["invoice_number"],
            "amount": f"{invoice['amount']:,.0f}",
            "due": invoice["due_on"].strftime("%d %b"),
            "payment_status": timing,
            "reminder_number": attempt,
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


async def campaign_message(payload: dict) -> SendResult:
    from genesis.domain import campaigns

    campaign_id = payload["campaign_id"]
    customer_id = payload["customer_id"]
    message_type = MessageType(payload["message_type"])

    row = await pool.fetchrow(
        """
        select c.full_name,
               max(a.starts_at) as last_service_at,
               (select s.name from appointments a2
                  join services s on s.id = a2.service_id
                 where a2.customer_id = c.id and a2.status = 'completed'
                 order by a2.starts_at desc limit 1) as last_service
          from customers c
          left join appointments a on a.customer_id = c.id and a.status = 'completed'
         where c.id = $1 and c.business_id = $2
         group by c.id
        """,
        customer_id,
        settings.demo_business_id,
    )
    if row is None:
        raise ValueError("Customer no longer exists")

    first_name = row["full_name"].split()[0]
    months = 0
    if row["last_service_at"]:
        months = max(1, int((datetime.now(UTC) - row["last_service_at"]).days / 30))

    context: dict[str, Any] = {
        MessageType.REACTIVATION: {"name": first_name, "months": months},
        MessageType.SEASONAL: {},
        MessageType.REVIEW_REQUEST: {
            "name": first_name,
            "service": row["last_service"] or "recent service",
        },
    }[message_type]

    result = await send_customer_message(
        business_id=settings.demo_business_id,
        customer_id=customer_id,
        message_type=message_type,
        context=context,
        dedupe_key=f"campaign:{campaign_id}",
        campaign_id=campaign_id,
    )

    # The recipient row records what actually happened, so a campaign that was
    # mostly refused reports that instead of claiming success.
    if result.sent:
        recipient_status = "sent"
    elif result.blocked:
        recipient_status = "blocked"
    else:
        recipient_status = "failed"

    await pool.execute(
        """
        update campaign_recipients
           set status = $3,
               block_reason = $4,
               sent_at = case when $3 = 'sent' then now() end
         where campaign_id = $1 and customer_id = $2
        """,
        campaign_id,
        customer_id,
        recipient_status,
        result.reason,
    )
    await campaigns.finalise_if_complete(campaign_id)
    return result


HANDLERS = {
    "appointment_confirmation": appointment_confirmation,
    "appointment_reminder": appointment_reminder,
    "post_service_followup": post_service_followup,
    "review_request": review_request,
    "invoice_sent": invoice_sent,
    "payment_reminder": payment_reminder,
    "campaign_message": campaign_message,
}
