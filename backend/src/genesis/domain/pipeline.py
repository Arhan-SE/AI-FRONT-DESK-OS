"""The job pipeline.

The owner reports what happened in the real world. The system decides what that
means. Nobody composes a message by hand.

    SCHEDULED → CONFIRMED → IN PROGRESS → COMPLETED → INVOICE SENT → PAID
                                                                   ↘ OVERDUE

Every transition is the *only* thing that enqueues outbound work, which makes
each message causally traceable to a human action. Enqueued work carries a
dedupe key, so a double-clicked button cannot produce two reminders.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import asyncpg

from genesis.db import pool
from genesis.domain.observability import decisions
from genesis.settings import settings

log = logging.getLogger(__name__)


class Stage(StrEnum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    INVOICE_SENT = "invoice_sent"
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    APPOINTMENT_CANCELLED = "appointment_cancelled"
    PAYMENT_RECEIVED = "payment_received"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class Action(StrEnum):
    CONFIRM = "confirm"
    START = "start"
    COMPLETE = "complete"
    SEND_INVOICE = "send_invoice"
    MARK_PAID = "mark_paid"
    CANCEL = "cancel"
    NO_SHOW = "no_show"


class JobType(StrEnum):
    APPOINTMENT_CONFIRMATION = "appointment_confirmation"
    APPOINTMENT_REMINDER = "appointment_reminder"
    INVOICE_SENT = "invoice_sent"
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    APPOINTMENT_CANCELLED = "appointment_cancelled"
    PAYMENT_RECEIVED = "payment_received"
    POST_SERVICE_FOLLOWUP = "post_service_followup"
    REVIEW_REQUEST = "review_request"
    PAYMENT_REMINDER = "payment_reminder"


class TransitionError(ValueError):
    """The requested action is not valid from the job's current state."""


# Which appointment statuses each action may be applied to. Deliberately
# permissive about skipping forward — an owner who forgot to press "Start"
# should still be able to press "Complete" — but never about going backwards.
ALLOWED_FROM: dict[Action, set[str]] = {
    Action.CONFIRM: {"booked"},
    Action.START: {"booked", "confirmed"},
    Action.COMPLETE: {"booked", "confirmed", "in_progress"},
    Action.CANCEL: {"booked", "confirmed", "in_progress"},
    Action.NO_SHOW: {"booked", "confirmed", "in_progress"},
    Action.SEND_INVOICE: {"completed"},
    Action.MARK_PAID: {"completed"},
}

NEW_STATUS: dict[Action, str] = {
    Action.CONFIRM: "confirmed",
    Action.START: "in_progress",
    Action.COMPLETE: "completed",
    Action.CANCEL: "cancelled",
    Action.NO_SHOW: "no_show",
}

STAMP_COLUMN: dict[Action, str] = {
    Action.CONFIRM: "confirmed_at",
    Action.START: "started_at",
    Action.COMPLETE: "completed_at",
    Action.CANCEL: "cancelled_at",
}


@dataclass(slots=True)
class TransitionResult:
    job_id: str
    action: Action
    stage: str
    enqueued: list[str]
    cancelled_jobs: int = 0


# --------------------------------------------------------------------------
# Enqueueing
# --------------------------------------------------------------------------


async def _enqueue(
    conn: asyncpg.Connection,
    *,
    job_type: JobType,
    scheduled_for: datetime,
    payload: dict,
    dedupe_key: str,
) -> bool:
    """Schedule automation work. Returns False if it was already scheduled.

    The partial unique index on automation_jobs is the real guarantee; ON
    CONFLICT DO NOTHING just turns a duplicate into a no-op instead of an error.
    """
    result = await conn.execute(
        """
        insert into automation_jobs
          (business_id, job_type, scheduled_for, payload, dedupe_key)
        values ($1, $2, $3, $4::jsonb, $5)
        on conflict do nothing
        """,
        settings.demo_business_id,
        job_type.value,
        scheduled_for,
        json.dumps(payload),
        dedupe_key,
    )
    return result.endswith("1")


async def _cancel_pending(conn: asyncpg.Connection, dedupe_prefix: str) -> int:
    """Stop work that is no longer appropriate — e.g. reminders after payment."""
    return int(
        await conn.fetchval(
            """
            with cancelled as (
              update automation_jobs
                 set status = 'cancelled', completed_at = now()
               where business_id = $1
                 and status = 'pending'
                 and dedupe_key like $2
              returning 1
            )
            select count(*) from cancelled
            """,
            settings.demo_business_id,
            f"{dedupe_prefix}%",
        )
        or 0
    )


# --------------------------------------------------------------------------
# Job creation
# --------------------------------------------------------------------------


async def create_job(
    *,
    customer_id: str,
    service_id: str,
    technician_id: str,
    starts_at: datetime,
    source: str = "manual",
    notes: str | None = None,
    idempotency_key: str | None = None,
) -> str:
    """Create a scheduled job.

    The exclusion constraint is the arbiter of whether the slot is free — this
    does not pre-check, because a check followed by an insert is exactly the
    race the constraint exists to eliminate.
    """
    async with pool.transaction() as conn:
        service = await conn.fetchrow(
            "select duration_minutes, buffer_minutes, name from services where id = $1",
            service_id,
        )
        if service is None:
            raise ValueError("Unknown service")

        ends_at = starts_at + timedelta(minutes=service["duration_minutes"])
        blocked_until = ends_at + timedelta(minutes=service["buffer_minutes"])

        try:
            job_id = await conn.fetchval(
                """
                insert into appointments
                  (business_id, customer_id, service_id, technician_id,
                   starts_at, ends_at, buffer_minutes, blocked_until,
                   status, source, notes, idempotency_key)
                values ($1,$2,$3,$4,$5,$6,$7,$8,'booked',$9,$10,$11)
                returning id
                """,
                settings.demo_business_id,
                customer_id,
                service_id,
                technician_id,
                starts_at,
                ends_at,
                service["buffer_minutes"],
                blocked_until,
                source,
                notes,
                idempotency_key,
            )
        except asyncpg.exceptions.ExclusionViolationError as exc:
            raise TransitionError(
                "That technician is already booked at that time"
            ) from exc

        await decisions.record(
            business_id=settings.demo_business_id,
            customer_id=customer_id,
            event_type="job_created",
            summary=f"Job scheduled — {service['name']}",
            detail={"job_id": str(job_id), "source": source},
            conn=conn,
        )
        return str(job_id)


# --------------------------------------------------------------------------
# Transitions
# --------------------------------------------------------------------------


async def transition(job_id: str, action: Action) -> TransitionResult:
    now = datetime.now(UTC)

    async with pool.transaction() as conn:
        job = await conn.fetchrow(
            """
            select a.id, a.status, a.customer_id, a.starts_at, a.completed_at,
                   s.name as service_name, s.base_price,
                   c.full_name as customer_name,
                   i.id as invoice_id, i.status as invoice_status
              from appointments a
              join services  s on s.id = a.service_id
              join customers c on c.id = a.customer_id
              left join invoices i on i.appointment_id = a.id
             where a.id = $1 and a.business_id = $2
             for update of a
            """,
            job_id,
            settings.demo_business_id,
        )
        if job is None:
            raise TransitionError("Job not found")

        allowed = ALLOWED_FROM[action]
        if job["status"] not in allowed:
            raise TransitionError(
                f"Cannot {action.value} a job that is {job['status']}"
            )

        enqueued: list[str] = []
        cancelled = 0

        # ---------------------------------------------------------- invoice
        if action is Action.SEND_INVOICE:
            if job["invoice_id"] is not None:
                raise TransitionError("An invoice already exists for this job")

            due_on = (now + timedelta(days=settings.invoice_due_days)).date()
            number = await _next_invoice_number(conn)

            invoice_id = await conn.fetchval(
                """
                insert into invoices
                  (business_id, customer_id, appointment_id, invoice_number,
                   amount, status, issued_on, due_on)
                values ($1,$2,$3,$4,$5,'sent',current_date,$6)
                returning id
                """,
                settings.demo_business_id,
                job["customer_id"],
                job_id,
                number,
                job["base_price"],
                due_on,
            )

            # The customer gets the bill now. "Send invoice" that sends nothing
            # to the customer is a button that lies about what it does.
            await _enqueue(
                conn,
                job_type=JobType.INVOICE_SENT,
                scheduled_for=now,
                payload={"invoice_id": str(invoice_id)},
                dedupe_key=f"invoice:{invoice_id}:issued",
            )
            enqueued.append("invoice_sent")

            # First reminder falls due the morning after the due date. Repeats
            # are scheduled by the job itself, so a paid invoice stops the chain.
            await _enqueue(
                conn,
                job_type=JobType.PAYMENT_REMINDER,
                scheduled_for=datetime.combine(
                    due_on + timedelta(days=1), datetime.min.time(), tzinfo=UTC
                ),
                payload={"invoice_id": str(invoice_id), "attempt": 1},
                dedupe_key=f"invoice:{invoice_id}:reminder:1",
            )
            enqueued.append("payment_reminder")

            await decisions.record(
                business_id=settings.demo_business_id,
                customer_id=str(job["customer_id"]),
                event_type="invoice_sent",
                summary=f"Invoice {number} raised — ₹{job['base_price']:,.0f}, due {due_on}",
                detail={"invoice_id": str(invoice_id), "due_on": str(due_on)},
                conn=conn,
            )
            return TransitionResult(job_id, action, Stage.INVOICE_SENT, enqueued)

        if action is Action.MARK_PAID:
            if job["invoice_id"] is None:
                raise TransitionError("No invoice to mark paid")

            await conn.execute(
                "update invoices set status = 'paid', paid_at = now() where id = $1",
                job["invoice_id"],
            )
            await conn.execute(
                """
                insert into payments (business_id, invoice_id, amount, method)
                select business_id, id, amount, 'cash' from invoices where id = $1
                """,
                job["invoice_id"],
            )
            # Chasing a paid invoice is the classic automation embarrassment.
            # Scoped to reminders only: the issuance notice under
            # `invoice:<id>:issued` is the bill itself, and cancelling that
            # because payment arrived first means the customer is never told
            # what they paid for.
            cancelled = await _cancel_pending(conn, f"invoice:{job['invoice_id']}:reminder")

            # Enqueued after the sweep, or it would cancel its own receipt.
            await _enqueue(
                conn,
                job_type=JobType.PAYMENT_RECEIVED,
                scheduled_for=now,
                payload={"invoice_id": str(job["invoice_id"])},
                dedupe_key=f"receipt:{job['invoice_id']}",
            )
            enqueued.append("payment_received")

            await decisions.record(
                business_id=settings.demo_business_id,
                customer_id=str(job["customer_id"]),
                event_type="payment_received",
                summary=f"Payment received — {job['customer_name']}",
                detail={"cancelled_reminders": cancelled},
                conn=conn,
            )
            return TransitionResult(job_id, action, Stage.PAID, enqueued, cancelled)

        # ------------------------------------------------- appointment moves
        new_status = NEW_STATUS[action]
        stamp = STAMP_COLUMN.get(action)

        if stamp:
            await conn.execute(
                f"update appointments set status = $2, {stamp} = $3 where id = $1",  # noqa: S608
                job_id,
                new_status,
                now,
            )
        else:
            await conn.execute(
                "update appointments set status = $2 where id = $1", job_id, new_status
            )

        if action is Action.CONFIRM:
            await _enqueue(
                conn,
                job_type=JobType.APPOINTMENT_CONFIRMATION,
                scheduled_for=now,
                payload={"appointment_id": job_id},
                dedupe_key=f"appointment:{job_id}:confirmation",
            )
            enqueued.append("appointment_confirmation")

            # Reminder the day before, only if that is still in the future.
            reminder_at = job["starts_at"] - timedelta(hours=24)
            if reminder_at > now:
                await _enqueue(
                    conn,
                    job_type=JobType.APPOINTMENT_REMINDER,
                    scheduled_for=reminder_at,
                    payload={"appointment_id": job_id},
                    dedupe_key=f"appointment:{job_id}:reminder",
                )
                enqueued.append("appointment_reminder")

        elif action is Action.START:
            await _enqueue(
                conn,
                job_type=JobType.JOB_STARTED,
                scheduled_for=now,
                payload={"appointment_id": job_id},
                dedupe_key=f"appointment:{job_id}:started",
            )
            enqueued.append("job_started")

        elif action is Action.COMPLETE:
            # A reminder for a job that has already happened is worse than no
            # reminder. Once the work is done, the pre-visit reminder is dead.
            cancelled = await _cancel_pending(conn, f"appointment:{job_id}:reminder")

            await _enqueue(
                conn,
                job_type=JobType.JOB_COMPLETED,
                scheduled_for=now,
                payload={"appointment_id": job_id},
                dedupe_key=f"appointment:{job_id}:completed",
            )
            await _enqueue(
                conn,
                job_type=JobType.POST_SERVICE_FOLLOWUP,
                scheduled_for=now + timedelta(hours=settings.followup_delay_hours),
                payload={"appointment_id": job_id},
                dedupe_key=f"appointment:{job_id}:followup",
            )
            await _enqueue(
                conn,
                job_type=JobType.REVIEW_REQUEST,
                scheduled_for=now + timedelta(hours=settings.review_delay_hours),
                payload={"appointment_id": job_id},
                dedupe_key=f"appointment:{job_id}:review",
            )
            enqueued += ["job_completed", "post_service_followup", "review_request"]

        elif action in (Action.CANCEL, Action.NO_SHOW):
            # Nothing scheduled for this job should still fire.
            cancelled = await _cancel_pending(conn, f"appointment:{job_id}:")

            # Queued after the sweep above, otherwise it cancels itself. A
            # no-show is the customer's absence, not ours — no apology sent.
            if action is Action.CANCEL:
                await _enqueue(
                    conn,
                    job_type=JobType.APPOINTMENT_CANCELLED,
                    scheduled_for=now,
                    payload={"appointment_id": job_id},
                    dedupe_key=f"cancelled:{job_id}",
                )
                enqueued.append("appointment_cancelled")

        await decisions.record(
            business_id=settings.demo_business_id,
            customer_id=str(job["customer_id"]),
            event_type=f"job_{action.value}",
            summary=_summary(action, job["customer_name"], job["service_name"]),
            detail={"job_id": job_id, "enqueued": enqueued, "cancelled": cancelled},
            conn=conn,
        )

        return TransitionResult(job_id, action, new_status, enqueued, cancelled)


# --------------------------------------------------------------------------
# Correction
# --------------------------------------------------------------------------
#
# Distinct from a transition on purpose. Transitions are the record of what
# happened in the real world and only move forward; a correction says the
# record was wrong. Conflating the two would make "cancel" and "I misclicked"
# indistinguishable in the audit trail.

# How far back each stage sits, so a correction knows what to undo.
_ORDER = [
    Stage.SCHEDULED,
    Stage.CONFIRMED,
    Stage.IN_PROGRESS,
    Stage.COMPLETED,
    Stage.INVOICE_SENT,
    Stage.PAID,
]

_APPOINTMENT_STATUS = {
    Stage.SCHEDULED: "booked",
    Stage.CONFIRMED: "confirmed",
    Stage.IN_PROGRESS: "in_progress",
    Stage.COMPLETED: "completed",
    Stage.INVOICE_SENT: "completed",
    Stage.PAID: "completed",
}


async def correct_stage(job_id: str, target: Stage) -> TransitionResult:
    """Move a job to an earlier stage, undoing what that stage set in motion.

    Messages already sent are not unsent — that is not possible, and pretending
    otherwise would be worse than admitting it. What this does undo is state
    and pending work: invoices, payments, and queued automations.
    """
    if target not in _ORDER:
        raise TransitionError(f"Cannot correct a job to '{target}'")

    async with pool.transaction() as conn:
        job = await conn.fetchrow(
            """
            select a.id, a.status, a.customer_id, c.full_name as customer_name,
                   s.name as service_name, i.id as invoice_id, i.status as invoice_status,
                   i.due_on
              from appointments a
              join customers c on c.id = a.customer_id
              join services  s on s.id = a.service_id
              left join invoices i on i.appointment_id = a.id
             where a.id = $1 and a.business_id = $2
             for update of a
            """,
            job_id,
            settings.demo_business_id,
        )
        if job is None:
            raise TransitionError("Job not found")

        undone: list[str] = []
        cancelled = 0

        # --- invoice-level undo -------------------------------------------
        if target in (Stage.SCHEDULED, Stage.CONFIRMED, Stage.IN_PROGRESS, Stage.COMPLETED):
            if job["invoice_id"]:
                await conn.execute(
                    "delete from payments where invoice_id = $1", job["invoice_id"]
                )
                await conn.execute("delete from invoices where id = $1", job["invoice_id"])
                cancelled += await _cancel_pending(conn, f"invoice:{job['invoice_id']}:reminder")
                undone.append("invoice removed")

        elif target is Stage.INVOICE_SENT and job["invoice_id"]:
            # Un-marking a payment: drop the payment record and put the invoice
            # back to whichever state its due date implies.
            await conn.execute("delete from payments where invoice_id = $1", job["invoice_id"])
            new_status = (
                "overdue" if job["due_on"] and job["due_on"] < datetime.now(UTC).date() else "sent"
            )
            await conn.execute(
                "update invoices set status = $2, paid_at = null where id = $1",
                job["invoice_id"],
                new_status,
            )
            undone.append(f"payment removed, invoice back to {new_status}")

            # Chasing resumes from the next unused attempt number.
            #
            # This must be derived from the jobs already created, not from
            # messages sent: a reminder that ran and was blocked still owns its
            # dedupe key, so reusing that number would be silently swallowed by
            # ON CONFLICT and queue nothing at all.
            highest = await conn.fetchval(
                """
                select coalesce(max(split_part(dedupe_key, ':', 4)::int), 0)
                  from automation_jobs
                 where business_id = $1
                   and job_type = 'payment_reminder'
                   and dedupe_key like $2
                """,
                settings.demo_business_id,
                f"invoice:{job['invoice_id']}:reminder:%",
            )
            attempt = int(highest or 0) + 1

            if attempt <= settings.max_payment_reminders:
                queued = await _enqueue(
                    conn,
                    job_type=JobType.PAYMENT_REMINDER,
                    scheduled_for=datetime.now(UTC) + timedelta(days=1),
                    payload={"invoice_id": str(job["invoice_id"]), "attempt": attempt},
                    dedupe_key=f"invoice:{job['invoice_id']}:reminder:{attempt}",
                )
                # Only claim what actually happened.
                if queued:
                    undone.append("payment reminder re-queued")
            else:
                undone.append(
                    f"no further reminders — {settings.max_payment_reminders} already used"
                )

        # --- appointment-level undo ---------------------------------------
        if target in (Stage.SCHEDULED, Stage.CONFIRMED, Stage.IN_PROGRESS):
            cancelled += await _cancel_pending(conn, f"appointment:{job_id}:followup")
            cancelled += await _cancel_pending(conn, f"appointment:{job_id}:review")
        if target in (Stage.SCHEDULED, Stage.CONFIRMED):
            await conn.execute(
                "delete from reviews where appointment_id = $1 and submitted_at is null",
                job_id,
            )
        if target is Stage.SCHEDULED:
            cancelled += await _cancel_pending(conn, f"appointment:{job_id}:")

        clears = {
            Stage.SCHEDULED: "confirmed_at = null, started_at = null, completed_at = null",
            Stage.CONFIRMED: "started_at = null, completed_at = null",
            Stage.IN_PROGRESS: "completed_at = null",
        }.get(target, "")

        try:
            await conn.execute(
                f"""update appointments
                       set status = $2, cancelled_at = null
                           {', ' + clears if clears else ''}
                     where id = $1""",  # noqa: S608 — clears is from the literal map above
                job_id,
                _APPOINTMENT_STATUS[target],
            )
        except asyncpg.exceptions.ExclusionViolationError as exc:
            # Re-activating a cancelled job can collide: someone else may have
            # taken the slot while it was free.
            raise TransitionError(
                "That technician is now booked at this time, so this job "
                "cannot be reopened. Reschedule it instead."
            ) from exc

        await decisions.record(
            business_id=settings.demo_business_id,
            customer_id=str(job["customer_id"]),
            event_type="job_corrected",
            status="pending",
            summary=(
                f"Stage corrected to {target.value.replace('_', ' ')} — "
                f"{job['service_name']} for {job['customer_name']}"
            ),
            detail={"job_id": job_id, "undone": undone, "cancelled_jobs": cancelled},
            conn=conn,
        )

        return TransitionResult(job_id, Action.CANCEL, target, undone, cancelled)


async def _next_invoice_number(conn: asyncpg.Connection) -> str:
    n = await conn.fetchval(
        """
        select coalesce(max(substring(invoice_number from 5)::int), 1000) + 1
          from invoices
         where business_id = $1 and invoice_number ~ '^INV-[0-9]+$'
        """,
        settings.demo_business_id,
    )
    return f"INV-{n}"


def _summary(action: Action, customer: str, service: str) -> str:
    return {
        Action.CONFIRM: f"Job confirmed — {service} for {customer}",
        Action.START: f"Technician started — {service} for {customer}",
        Action.COMPLETE: f"Job completed — {service} for {customer}",
        Action.CANCEL: f"Job cancelled — {service} for {customer}",
        Action.NO_SHOW: f"Customer no-show — {service} for {customer}",
    }[action]
