"""Slot holds and booking.

Holds exist because of how a phone call actually works:

    agent: "I have Tuesday at nine, Wednesday at twelve, or Thursday morning."
    customer: "...let me check with my wife... yeah, Wednesday."   <- 25 seconds
    agent: books Wednesday

Without a hold, another conversation can take Wednesday while the customer is
still deciding, and the agent confidently books something that no longer
exists. The hold makes the offer real for three minutes.

If the hold has expired by the time they choose, the booking is refused rather
than attempted blindly. The agent re-checks and offers fresh times.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg

from genesis.db import pool
from genesis.domain.observability import decisions
from genesis.domain.scheduling.availability import Slot
from genesis.settings import settings

log = logging.getLogger(__name__)


class BookingError(Exception):
    """Something prevented the booking. The message is safe to speak aloud."""


@dataclass(slots=True)
class HeldSlot:
    hold_id: str
    spoken: str
    technician_name: str
    starts_at: datetime


async def hold(
    slots: list[Slot],
    *,
    conversation_id: str | None = None,
    customer_id: str | None = None,
) -> list[HeldSlot]:
    """Reserve the offered slots for a short TTL.

    A hold that clashes is skipped rather than raising: another conversation
    got there first, and the customer should simply be offered the rest.
    """
    expires = datetime.now(UTC) + timedelta(seconds=settings.slot_hold_ttl_seconds)
    held: list[HeldSlot] = []

    async with pool.connection() as conn:
        for slot in slots:
            try:
                hold_id = await conn.fetchval(
                    """
                    insert into slot_holds
                      (business_id, technician_id, service_id, customer_id,
                       conversation_id, starts_at, ends_at, buffer_minutes,
                       blocked_until, expires_at)
                    select $1, $2, $3, $4, $5, $6, $7, s.buffer_minutes, $8, $9
                      from services s where s.id = $3
                    returning id
                    """,
                    settings.demo_business_id,
                    slot.technician_id,
                    slot.service_id,
                    customer_id,
                    conversation_id,
                    slot.starts_at,
                    slot.ends_at,
                    slot.blocked_until,
                    expires,
                )
            except asyncpg.exceptions.ExclusionViolationError:
                log.info("slot taken while offering: %s", slot.starts_at)
                continue

            held.append(
                HeldSlot(
                    hold_id=str(hold_id),
                    spoken=slot.spoken(),
                    technician_name=slot.technician_name,
                    starts_at=slot.starts_at,
                )
            )
    return held


async def book(
    *,
    hold_id: str,
    customer_id: str,
    notes: str | None = None,
    conversation_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Convert a live hold into an appointment.

    The exclusion constraint is the final arbiter. Everything before it is
    optimistic; this is the step that cannot be raced.
    """
    async with pool.transaction() as conn:
        held = await conn.fetchrow(
            """
            select h.*, s.name as service_name, t.full_name as technician_name
              from slot_holds h
              join services s on s.id = h.service_id
              join technicians t on t.id = h.technician_id
             where h.id = $1 and h.business_id = $2
             for update of h
            """,
            hold_id,
            settings.demo_business_id,
        )

        if held is None:
            raise BookingError("That time is no longer being held. Let me check again.")
        if held["consumed_at"] is not None:
            raise BookingError("That slot has already been booked.")
        if held["expires_at"] < datetime.now(UTC):
            raise BookingError(
                "That time expired while we were talking. Let me find fresh options."
            )

        try:
            appointment_id = await conn.fetchval(
                """
                insert into appointments
                  (business_id, customer_id, service_id, technician_id,
                   starts_at, ends_at, buffer_minutes, blocked_until,
                   status, source, notes, idempotency_key)
                values ($1,$2,$3,$4,$5,$6,$7,$8,'booked','voice',$9,$10)
                returning id
                """,
                settings.demo_business_id,
                customer_id,
                held["service_id"],
                held["technician_id"],
                held["starts_at"],
                held["ends_at"],
                held["buffer_minutes"],
                held["blocked_until"],
                notes,
                idempotency_key,
            )
        except asyncpg.exceptions.ExclusionViolationError as exc:
            raise BookingError(
                "Someone just took that time. Let me find you another."
            ) from exc
        except asyncpg.exceptions.UniqueViolationError:
            # Same idempotency key: a retry, not a second booking.
            existing = await conn.fetchval(
                "select id from appointments where business_id = $1 and idempotency_key = $2",
                settings.demo_business_id,
                idempotency_key,
            )
            appointment_id = existing

        await conn.execute(
            "update slot_holds set consumed_at = now() where id = $1", hold_id
        )
        # Everything else offered in this conversation is now dead weight.
        if conversation_id:
            await conn.execute(
                """delete from slot_holds
                    where conversation_id = $1 and consumed_at is null and id <> $2""",
                conversation_id,
                hold_id,
            )

        local = held["starts_at"].astimezone(settings.tz)
        await decisions.record(
            business_id=settings.demo_business_id,
            customer_id=customer_id,
            conversation_id=conversation_id,
            event_type="appointment_booked",
            summary=(
                f"Booked {held['service_name']} on "
                f"{local:%A %d %b at %I:%M %p} with {held['technician_name']}"
            ),
            detail={"appointment_id": str(appointment_id)},
            tool_name="book_appointment",
            conn=conn,
        )

        return {
            "appointment_id": str(appointment_id),
            "service": held["service_name"],
            "technician": held["technician_name"],
            "when": f"{local:%A %d %B at %I:%M %p}".replace(" 0", " "),
        }


async def release(conversation_id: str) -> int:
    """Drop every unconsumed hold from a conversation, e.g. when a call ends."""
    result = await pool.execute(
        "delete from slot_holds where conversation_id = $1 and consumed_at is null",
        conversation_id,
    )
    return int(result.split()[-1]) if result.startswith("DELETE") else 0
