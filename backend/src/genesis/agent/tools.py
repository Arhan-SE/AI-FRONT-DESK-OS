"""The receptionist's tools.

Plain async functions operating on explicit state, deliberately separate from
the LiveKit wiring. That separation is what lets every one of them be tested
against the real database before a microphone is involved — and it means a
failure in voice transport cannot be confused with a failure in booking logic.

Every function returns a string, because the caller is a speech model. A dict
would be read aloud as JSON.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from genesis.db import pool
from genesis.domain.observability import decisions
from genesis.domain.scheduling import availability, booking
from genesis.settings import settings

log = logging.getLogger("genesis.agent.tools")

# Deterministic. Not a model decision — a tripwire the model cannot decline to
# trigger, because it is evaluated on the transcript rather than chosen.
DANGER = re.compile(
    r"\b(gas leak|gas smell|smell(?:ing)? gas|burning smell|smoke|sparking|"
    r"sparks|carbon monoxide|flooding|electric shock|fire)\b",
    re.IGNORECASE,
)

SAFETY_RESPONSE = (
    "That sounds dangerous. Please hang up and call emergency services right "
    "away — I'm not able to help with something like this, and it shouldn't "
    "wait."
)


@dataclass
class SessionState:
    """Conversation state. The backend is authoritative, not the model's memory."""

    conversation_id: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    service_id: str | None = None
    service_name: str | None = None
    offered: list[booking.HeldSlot] = field(default_factory=list)
    found_appointment_id: str | None = None
    safety_triggered: bool = False


async def _log(state: SessionState, event: str, summary: str, **detail) -> None:
    await decisions.record(
        business_id=settings.demo_business_id,
        conversation_id=state.conversation_id,
        customer_id=state.customer_id,
        event_type=event,
        summary=summary,
        detail=detail,
        tool_name=event,
    )


# ---------------------------------------------------------------- identity


async def identify_customer(state: SessionState, name: str, phone: str = "") -> str:
    """Find the caller, or create them. Returns a line the agent can speak from."""
    name = name.strip()
    if not name:
        return "Ask the caller for their name."

    async with pool.connection() as conn:
        row = await conn.fetchrow(
            """
            select id, full_name,
                   (select count(*) from appointments a
                     where a.customer_id = c.id and a.status = 'completed') as visits,
                   (select s.name from appointments a join services s on s.id = a.service_id
                     where a.customer_id = c.id and a.status = 'completed'
                     order by a.starts_at desc limit 1) as last_service
              from customers c
             where c.business_id = $1 and lower(c.full_name) = lower($2)
             limit 1
            """,
            settings.demo_business_id,
            name,
        )

        if row is None:
            row = await conn.fetchrow(
                """
                insert into customers (business_id, full_name, phone, status)
                values ($1, $2, $3, 'active')
                returning id, full_name, 0 as visits, null::text as last_service
                """,
                settings.demo_business_id,
                name,
                phone.strip() or None,
            )
            state.customer_id = str(row["id"])
            state.customer_name = row["full_name"]
            if state.conversation_id:
                await pool.execute(
                    "update conversations set customer_id = $2 where id = $1",
                    state.conversation_id,
                    state.customer_id,
                )
            await _log(state, "customer_created", f"New customer created — {name}")
            return f"New customer {name}. They have not used us before."

    state.customer_id = str(row["id"])
    state.customer_name = row["full_name"]
    if state.conversation_id:
        await pool.execute(
            "update conversations set customer_id = $2 where id = $1",
            state.conversation_id,
            state.customer_id,
        )

    await _log(
        state,
        "customer_identified",
        f"Identified {row['full_name']} — {row['visits']} previous job(s)",
        visits=row["visits"],
    )

    if row["visits"] and row["last_service"]:
        return (
            f"Returning customer {row['full_name']}, {row['visits']} previous "
            f"job(s), most recently {row['last_service']}."
        )
    return f"Known customer {row['full_name']}, no completed jobs yet."


# ---------------------------------------------------------------- services


async def list_services(state: SessionState) -> str:
    rows = await pool.fetch(
        """select name, duration_minutes, base_price from services
            where business_id = $1 and is_active order by base_price""",
        settings.demo_business_id,
    )
    await _log(state, "services_listed", "Service list retrieved")
    return " ".join(
        f"{r['name']}, {r['duration_minutes']} minutes, "
        f"{int(r['base_price'])} rupees."
        for r in rows
    )


# ---------------------------------------------------------------- slots


async def find_slots(state: SessionState, service: str, preferred_time: str = "") -> str:
    """Look up real availability and hold what is offered."""
    row = await pool.fetchrow(
        """select id, name from services
            where business_id = $1 and is_active and lower(name) like '%' || lower($2) || '%'
            order by length(name) limit 1""",
        settings.demo_business_id,
        service.strip(),
    )
    if row is None:
        names = await pool.fetch(
            "select name from services where business_id = $1 and is_active",
            settings.demo_business_id,
        )
        return (
            "No service matches that. We offer: "
            + ", ".join(r["name"] for r in names)
            + ". Ask which they want."
        )

    state.service_id = str(row["id"])
    state.service_name = row["name"]

    window = None
    lowered = preferred_time.lower()
    for w in ("morning", "afternoon", "evening"):
        if w in lowered:
            window = w
            break

    slots = await availability.compute(
        service_id=state.service_id,
        days_ahead=7,
        preferred_window=window,
        limit=settings.max_slots_offered,
    )
    if not slots:
        await _log(state, "availability_checked", f"No availability for {row['name']}")
        return "There is nothing available in the next week. Offer to take a message."

    # Holding is what makes the offer real for the length of the conversation.
    state.offered = await booking.hold(
        slots,
        conversation_id=state.conversation_id,
        customer_id=state.customer_id,
    )
    if not state.offered:
        return "Those times were just taken. Say you will look again."

    await _log(
        state,
        "availability_checked",
        f"Offered {len(state.offered)} time(s) for {row['name']}",
        options=[h.spoken for h in state.offered],
    )
    return "Offer these, numbered: " + "; ".join(
        f"option {i + 1}, {h.spoken} with {h.technician_name}"
        for i, h in enumerate(state.offered)
    )


async def confirm_booking(state: SessionState, option: int) -> str:
    if not state.customer_id:
        return "You do not know who this is yet. Ask for their name first."
    if not state.offered:
        return "No times have been offered yet. Look up availability first."
    if not 1 <= option <= len(state.offered):
        return f"There are only {len(state.offered)} options. Ask them to choose again."

    held = state.offered[option - 1]
    try:
        result = await booking.book(
            hold_id=held.hold_id,
            customer_id=state.customer_id,
            conversation_id=state.conversation_id,
        )
    except booking.BookingError as exc:
        state.offered = []
        await _log(state, "booking_failed", f"Booking failed — {exc}")
        # The message is written to be safe to say out loud.
        return f"{exc} Look up availability again."

    state.offered = []
    return (
        f"Booked. Confirm to the customer: {result['service']} on "
        f"{result['when']} with {result['technician']}."
    )


# ------------------------------------------------------------ existing job


async def find_my_appointment(state: SessionState) -> str:
    if not state.customer_id:
        return "You do not know who this is yet. Ask for their name first."

    row = await pool.fetchrow(
        """
        select a.id, a.starts_at, s.name as service, t.full_name as technician
          from appointments a
          join services s on s.id = a.service_id
          join technicians t on t.id = a.technician_id
         where a.business_id = $1 and a.customer_id = $2
           and a.status in ('booked','confirmed')
           and a.starts_at > now()
         order by a.starts_at limit 1
        """,
        settings.demo_business_id,
        state.customer_id,
    )
    if row is None:
        state.found_appointment_id = None
        return "They have no upcoming booking. Offer to make one."

    state.found_appointment_id = str(row["id"])
    local = row["starts_at"].astimezone(settings.tz)
    await _log(state, "appointment_found", f"Found booking on {local:%A %d %b}")
    return (
        f"They have {row['service']} on {local:%A %d %B at %I:%M %p} with "
        f"{row['technician']}. Confirm this is the one they mean."
    ).replace(" 0", " ")


async def cancel_my_appointment(state: SessionState) -> str:
    if not state.found_appointment_id:
        return "Find their booking first."

    from genesis.domain import pipeline

    try:
        await pipeline.transition(state.found_appointment_id, pipeline.Action.CANCEL)
    except pipeline.TransitionError as exc:
        return f"Could not cancel: {exc}"

    state.found_appointment_id = None
    await _log(state, "appointment_cancelled", "Booking cancelled by customer on a call")
    return "Cancelled. Confirm it is cancelled and ask if they want to rebook."


async def move_appointment(state: SessionState, option: int) -> str:
    """Reschedule: book the new time, then cancel the old one."""
    if not state.found_appointment_id:
        return "Find their booking first."
    if not state.offered:
        return "No new times offered yet. Look up availability first."
    if not 1 <= option <= len(state.offered):
        return f"There are only {len(state.offered)} options."

    old_id = state.found_appointment_id
    held = state.offered[option - 1]

    # New booking first. If it fails, the customer still has their original
    # slot — cancelling first would leave them with nothing.
    try:
        result = await booking.book(
            hold_id=held.hold_id,
            customer_id=state.customer_id,
            conversation_id=state.conversation_id,
        )
    except booking.BookingError as exc:
        state.offered = []
        return f"{exc} Their original booking is unchanged. Look up times again."

    from genesis.domain import pipeline

    try:
        await pipeline.transition(old_id, pipeline.Action.CANCEL)
    except pipeline.TransitionError:
        log.exception("rescheduled but could not cancel old appointment %s", old_id)

    state.offered = []
    state.found_appointment_id = None
    await _log(state, "appointment_rescheduled", f"Moved booking to {result['when']}")
    return (
        f"Moved. Confirm: {result['service']} is now on {result['when']} "
        f"with {result['technician']}."
    )


# ---------------------------------------------------------------- safety


def check_safety(text: str) -> str | None:
    """Deterministic tripwire. Returns what must be said, or None."""
    return SAFETY_RESPONSE if DANGER.search(text) else None
