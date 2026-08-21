"""Calendar subscription feeds.

Publishes the appointment book as iCalendar so a technician can subscribe in
whatever calendar app they already use. Read-only and one-way by design: the
database stays the single source of truth, and nothing a calendar client does
can move a booking. The exclusion constraint on `appointments` remains the only
authority on what is booked.

Authentication is the URL. A calendar client fetches unattended on a timer and
cannot log in, so the token in the path is the credential — it identifies one
feed, grants nothing else, and is revoked by updating one column.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Response

from genesis.db import pool
from genesis.domain.scheduling import icalendar as ics
from genesis.settings import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/calendar", tags=["calendar"])

# How much of the book to publish. Far enough back that a technician can check
# what they did last month, far enough forward to cover anything booked.
PAST_DAYS = 60
FUTURE_DAYS = 180

# A calendar shows a booking as tentative until the customer confirms, which is
# exactly the distinction the pipeline already tracks.
_STATUS = {
    "booked": "TENTATIVE",
    "confirmed": "CONFIRMED",
    "in_progress": "CONFIRMED",
    "completed": "CONFIRMED",
    "cancelled": "CANCELLED",
    "no_show": "CANCELLED",
}

_QUERY = """
select a.id, a.starts_at, a.ends_at, a.status, a.notes,
       a.created_at, a.updated_at,
       c.full_name as customer_name, c.phone as customer_phone,
       c.address  as customer_address,
       s.name     as service_name,
       t.full_name as technician_name
  from appointments a
  join customers   c on c.id = a.customer_id
  join services    s on s.id = a.service_id
  join technicians t on t.id = a.technician_id
 where a.business_id = $1
   and ($2::uuid is null or a.technician_id = $2::uuid)
   and a.starts_at between $3 and $4
 order by a.starts_at
"""


def _to_event(row, *, include_technician: bool) -> ics.CalendarEvent:
    who = row["customer_name"]
    summary = f"{row['service_name']} — {who}"
    if include_technician:
        summary = f"{summary} ({row['technician_name']})"

    detail = [
        f"Customer: {who}",
        f"Service: {row['service_name']}",
        f"Technician: {row['technician_name']}",
        f"Status: {row['status'].replace('_', ' ')}",
    ]
    if row["customer_phone"]:
        detail.append(f"Phone: {row['customer_phone']}")
    if row["notes"]:
        detail.append(f"Notes: {row['notes']}")

    # SEQUENCE must rise whenever the event changes or clients ignore the
    # update. Seconds-since-created is monotonic per event and stays small,
    # unlike a raw epoch which would eventually overflow the field.
    sequence = int((row["updated_at"] - row["created_at"]).total_seconds())

    return ics.CalendarEvent(
        # Stable across refreshes, so a reschedule moves the existing event
        # instead of leaving a duplicate behind.
        uid=f"appointment-{row['id']}@genesis-os",
        starts_at=row["starts_at"],
        ends_at=row["ends_at"],
        summary=summary,
        description="\n".join(detail),
        location=row["customer_address"] or "",
        status=_STATUS.get(row["status"], "CONFIRMED"),
        sequence=max(sequence, 0),
        last_modified=row["updated_at"],
    )


@router.get("/{token}.ics")
async def feed(token: str) -> Response:
    """Serve one calendar feed. The token identifies whose it is."""
    now = datetime.now(UTC)
    window = (now - timedelta(days=PAST_DAYS), now + timedelta(days=FUTURE_DAYS))

    technician = await pool.fetchrow(
        """select id, business_id, full_name from technicians
            where calendar_token = $1""",
        token,
    )
    business = None
    if technician is None:
        business = await pool.fetchrow(
            "select id, name from businesses where calendar_token = $1", token
        )

    if technician is None and business is None:
        # 404 rather than 403: an unknown token should look identical to a feed
        # that does not exist, so probing cannot distinguish the two.
        return Response(status_code=404, content="Not found", media_type="text/plain")

    business_id = str(technician["business_id"] if technician else business["id"])
    rows = await pool.fetch(
        _QUERY,
        business_id,
        str(technician["id"]) if technician else None,
        *window,
    )

    if technician:
        name = f"{technician['full_name']} — Apex Climate Care"
        description = f"Scheduled jobs for {technician['full_name']}"
    else:
        name = f"{business['name']} — All jobs"
        description = "Every scheduled job across all technicians"

    body = ics.render(
        [_to_event(r, include_technician=business is not None) for r in rows],
        calendar_name=name,
        description=description,
    )

    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            # Subscribed feeds are polled; a cached copy would hide new bookings.
            "Cache-Control": "no-cache, max-age=0",
            "Content-Disposition": f'inline; filename="{token[:8]}.ics"',
        },
    )


@router.get("/feeds")
async def feeds() -> dict:
    """The subscription URLs, for the Settings page.

    Kept off the browser's direct-read path deliberately: these tokens are
    credentials, and the read path runs under the anon role.
    """
    base = settings.api_base_url.rstrip("/")

    business = await pool.fetchrow(
        "select name, calendar_token from businesses where id = $1",
        settings.demo_business_id,
    )
    technicians = await pool.fetch(
        """select full_name, calendar_token from technicians
            where business_id = $1 and is_active order by full_name""",
        settings.demo_business_id,
    )

    return {
        "business": {
            "name": f"{business['name']} — All jobs",
            "url": f"{base}/api/calendar/{business['calendar_token']}.ics",
        },
        "technicians": [
            {
                "name": t["full_name"],
                "url": f"{base}/api/calendar/{t['calendar_token']}.ics",
            }
            for t in technicians
        ],
    }
