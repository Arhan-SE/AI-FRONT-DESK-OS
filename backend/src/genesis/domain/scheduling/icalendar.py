"""iCalendar (RFC 5545) serialisation.

Turns appointments into a calendar feed that Google Calendar, Apple Calendar and
Outlook can subscribe to. Written by hand rather than pulled from a library: the
subset of RFC 5545 needed to publish read-only events is small, and it is a
subset that has to be exactly right — the failure mode of a malformed feed is a
calendar client that silently shows nothing.

Three details matter more than they look:

**UID must be stable.** A client matches events across refreshes by UID. Derive
it from the appointment id and a reschedule moves the existing event; derive it
from anything that changes and every refresh leaves a duplicate behind.

**SEQUENCE must increase when an event changes.** Clients ignore an update whose
sequence has not moved, so a rescheduled job would keep showing its old time.

**Cancelled events must still be published**, as STATUS:CANCELLED. Dropping the
event from the feed leaves it sitting on the technician's phone forever — the
client has no way to distinguish "removed" from "not in this window".

This module is pure: appointments in, text out. It reads no database and makes
no decisions about what should be published.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

PRODID = "-//Genesis OS//Home Service Operations//EN"

# RFC 5545 §3.1: lines are folded at 75 octets. Multi-byte characters must not
# be split across the fold, so folding counts encoded bytes, not characters.
_FOLD_LIMIT = 75


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """One appointment, in the shape a calendar needs."""

    uid: str
    starts_at: datetime
    ends_at: datetime
    summary: str
    description: str = ""
    location: str = ""
    status: str = "CONFIRMED"  # CONFIRMED | TENTATIVE | CANCELLED
    sequence: int = 0
    last_modified: datetime | None = None


def _escape(value: str) -> str:
    """Escape a TEXT value. Order matters — backslash first, or it double-escapes."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold one content line to 75 octets, continuing with a leading space."""
    encoded = line.encode("utf-8")
    if len(encoded) <= _FOLD_LIMIT:
        return line

    chunks: list[bytes] = []
    remaining = encoded
    limit = _FOLD_LIMIT
    while len(remaining) > limit:
        # Never split a multi-byte character: continuation bytes are 0b10xxxxxx,
        # so walk back until the cut lands on a leading byte.
        cut = limit
        while cut > 0 and (remaining[cut] & 0xC0) == 0x80:
            cut -= 1
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
        limit = _FOLD_LIMIT - 1  # continuation lines lose one octet to the space
    chunks.append(remaining)

    return "\r\n ".join(chunk.decode("utf-8") for chunk in chunks)


def _utc(moment: datetime) -> str:
    """Format as a UTC timestamp. Everything is published in UTC.

    Local times would need a VTIMEZONE component defining the offset and its
    transitions, and getting that subtly wrong shifts every appointment by an
    hour twice a year. UTC has no such failure mode; clients render it in
    whatever zone the viewer is in, which is what a technician wants anyway.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def render(
    events: Iterable[CalendarEvent],
    *,
    calendar_name: str,
    description: str = "",
    refresh_minutes: int = 15,
) -> str:
    """Render a complete VCALENDAR document."""
    now = _utc(datetime.now(UTC))

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        # X-WR-CALNAME is not in the standard, but every major client reads it
        # and without one the calendar shows up named after its URL.
        f"X-WR-CALNAME:{_escape(calendar_name)}",
        f"NAME:{_escape(calendar_name)}",
        # A hint, not a promise — clients refresh on their own schedule.
        f"REFRESH-INTERVAL;VALUE=DURATION:PT{refresh_minutes}M",
        f"X-PUBLISHED-TTL:PT{refresh_minutes}M",
    ]
    if description:
        lines.append(f"X-WR-CALDESC:{_escape(description)}")
        lines.append(f"DESCRIPTION:{_escape(description)}")

    for event in events:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{event.uid}",
                f"DTSTAMP:{now}",
                f"DTSTART:{_utc(event.starts_at)}",
                f"DTEND:{_utc(event.ends_at)}",
                f"SUMMARY:{_escape(event.summary)}",
                f"STATUS:{event.status}",
                f"SEQUENCE:{event.sequence}",
                "TRANSP:OPAQUE",
            ]
        )
        if event.description:
            lines.append(f"DESCRIPTION:{_escape(event.description)}")
        if event.location:
            lines.append(f"LOCATION:{_escape(event.location)}")
        if event.last_modified:
            lines.append(f"LAST-MODIFIED:{_utc(event.last_modified)}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    # RFC 5545 §3.1 requires CRLF line endings, and a trailing one.
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
