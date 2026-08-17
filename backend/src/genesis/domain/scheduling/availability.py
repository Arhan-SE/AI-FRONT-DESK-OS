"""Availability computation.

Availability is derived on every request, never stored. There is no "free
slots" table to drift out of sync with reality — the answer is always computed
from opening hours, technician schedules, time off, existing appointments and
live holds.

All arithmetic happens in the business's timezone and is converted to UTC at
the boundary. Asia/Kolkata is UTC+05:30, a half-hour offset, which is exactly
the kind of thing that silently produces 03:00 appointment offers if the
conversion is done carelessly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from genesis.db import pool
from genesis.settings import settings

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Slot:
    service_id: str
    technician_id: str
    technician_name: str
    starts_at: datetime          # UTC
    ends_at: datetime            # UTC
    blocked_until: datetime      # UTC, includes the service buffer

    @property
    def local(self) -> datetime:
        return self.starts_at.astimezone(settings.tz)

    def spoken(self) -> str:
        """Natural language for the voice agent. Never an ID or a timestamp."""
        d = self.local
        hour = d.hour
        if hour < 12:
            part = "in the morning"
        elif hour < 16:
            part = "in the afternoon"
        else:
            part = "in the evening"

        minute = f":{d.minute:02d}" if d.minute else ""
        hour12 = hour % 12 or 12
        today = datetime.now(settings.tz).date()

        if d.date() == today:
            day = "today"
        elif d.date() == today + timedelta(days=1):
            day = "tomorrow"
        else:
            day = d.strftime("%A")

        return f"{day} at {hour12}{minute} {part}"


@dataclass(slots=True)
class _Busy:
    start: datetime
    end: datetime


def _overlaps(a_start: datetime, a_end: datetime, busy: list[_Busy]) -> bool:
    return any(a_start < b.end and b.start < a_end for b in busy)


async def compute(
    *,
    service_id: str,
    days_ahead: int = 7,
    preferred_window: str | None = None,
    limit: int = 3,
) -> list[Slot]:
    """Find bookable slots for a service.

    preferred_window is a soft filter: matching slots are offered first, but if
    none exist the customer is offered something rather than nothing.
    """
    async with pool.connection() as conn:
        service = await conn.fetchrow(
            """select id, name, duration_minutes, buffer_minutes, required_skill
                 from services where id = $1 and business_id = $2 and is_active""",
            service_id,
            settings.demo_business_id,
        )
        if service is None:
            return []

        duration = timedelta(minutes=service["duration_minutes"])
        buffer = timedelta(minutes=service["buffer_minutes"])

        hours = {
            r["weekday"]: r
            for r in await conn.fetch(
                "select weekday, opens_at, closes_at, is_closed from business_hours "
                "where business_id = $1",
                settings.demo_business_id,
            )
        }
        holidays = {
            r["holiday_on"]
            for r in await conn.fetch(
                "select holiday_on from business_holidays where business_id = $1",
                settings.demo_business_id,
            )
        }

        technicians = await conn.fetch(
            """select t.id, t.full_name, t.skills
                 from technicians t
                where t.business_id = $1 and t.is_active
                order by t.full_name""",
            settings.demo_business_id,
        )
        schedules: dict[tuple[str, int], tuple[time, time]] = {
            (str(r["technician_id"]), r["weekday"]): (r["starts_at"], r["ends_at"])
            for r in await conn.fetch(
                "select technician_id, weekday, starts_at, ends_at "
                "from technician_schedules where business_id = $1",
                settings.demo_business_id,
            )
        }

        horizon_start = datetime.now(UTC)
        horizon_end = horizon_start + timedelta(days=days_ahead + 1)

        # Everything that already occupies a technician: booked work and live
        # offers. Holds are included so two conversations cannot be offered the
        # same time.
        busy: dict[str, list[_Busy]] = {}
        for row in await conn.fetch(
            """
            select technician_id, starts_at, blocked_until from appointments
             where business_id = $1 and status in ('booked','confirmed','in_progress')
               and starts_at < $3 and blocked_until > $2
            union all
            select technician_id, starts_at, blocked_until from slot_holds
             where business_id = $1 and consumed_at is null and expires_at > now()
               and starts_at < $3 and blocked_until > $2
            union all
            select technician_id, starts_at, ends_at from technician_time_off
             where business_id = $1 and starts_at < $3 and ends_at > $2
            """,
            settings.demo_business_id,
            horizon_start,
            horizon_end,
        ):
            busy.setdefault(str(row["technician_id"]), []).append(
                _Busy(row["starts_at"], row["blocked_until"])
            )

    # Never offer something the business cannot realistically reach.
    earliest = datetime.now(UTC) + timedelta(minutes=settings.min_booking_lead_minutes)
    grid = timedelta(minutes=settings.slot_granularity_minutes)
    today_local = datetime.now(settings.tz).date()

    preferred: list[Slot] = []
    fallback: list[Slot] = []

    for offset in range(days_ahead + 1):
        day: date = today_local + timedelta(days=offset)

        if day in holidays:
            continue
        # extract(dow) and Python's weekday() disagree; business_hours uses the
        # Postgres convention where Sunday is 0.
        weekday = (day.weekday() + 1) % 7
        opening = hours.get(weekday)
        if opening is None or opening["is_closed"]:
            continue

        for tech in technicians:
            tech_id = str(tech["id"])
            if service["required_skill"] and service["required_skill"] not in (
                tech["skills"] or []
            ):
                continue

            shift = schedules.get((tech_id, weekday))
            if shift is None:
                continue

            window_open = max(shift[0], opening["opens_at"])
            window_close = min(shift[1], opening["closes_at"])
            if window_open >= window_close:
                continue

            cursor = datetime.combine(day, window_open, tzinfo=settings.tz)
            close_at = datetime.combine(day, window_close, tzinfo=settings.tz)

            while cursor + duration <= close_at:
                start_utc = cursor.astimezone(UTC)
                end_utc = start_utc + duration
                blocked_utc = end_utc + buffer

                if start_utc >= earliest and not _overlaps(
                    start_utc, blocked_utc, busy.get(tech_id, [])
                ):
                    slot = Slot(
                        service_id=str(service["id"]),
                        technician_id=tech_id,
                        technician_name=tech["full_name"],
                        starts_at=start_utc,
                        ends_at=end_utc,
                        blocked_until=blocked_utc,
                    )
                    hour = cursor.hour
                    matches = (
                        preferred_window is None
                        or (preferred_window == "morning" and hour < 12)
                        or (preferred_window == "afternoon" and 12 <= hour < 16)
                        or (preferred_window == "evening" and hour >= 16)
                    )
                    (preferred if matches else fallback).append(slot)

                cursor += grid

    return _spread(preferred, fallback, limit)


# Offers must be genuinely different times. Three technicians free at 2:45 is
# one option, not three, and 9:00/9:15/9:30 is a customer's idea of no choice.
_MIN_GAP = timedelta(minutes=90)


def _spread(preferred: list[Slot], fallback: list[Slot], limit: int) -> list[Slot]:
    def pick(slots: list[Slot], already: list[Slot]) -> list[Slot]:
        chosen = list(already)
        # One technician per distinct start time; earliest-listed wins.
        by_time: dict[datetime, Slot] = {}
        for s in sorted(slots, key=lambda x: (x.starts_at, x.technician_name)):
            by_time.setdefault(s.starts_at, s)

        for start in sorted(by_time):
            if len(chosen) >= limit:
                break
            candidate = by_time[start]
            # Spread across the day, and never twice in the same hour.
            if any(
                abs(candidate.starts_at - c.starts_at) < _MIN_GAP for c in chosen
            ):
                continue
            chosen.append(candidate)
        return chosen

    chosen = pick(preferred, [])
    if len(chosen) < limit:
        chosen = pick(fallback, chosen)
    return chosen[:limit]
