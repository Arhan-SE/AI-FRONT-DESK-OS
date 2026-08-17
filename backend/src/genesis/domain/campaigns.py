"""Campaigns — bulk outreach that still passes the Communication Guard.

The valuable part here is `preview`. Because the Guard is a pure decision with
no side effects, it can be run over an audience *before* anything is sent,
producing a per-customer verdict with a stated reason. The owner sees "12
selected, 3 eligible, 9 blocked and here is why" before committing, instead of
discovering it afterwards in a log.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from genesis.db import pool
from genesis.domain.communication import guard
from genesis.domain.communication.types import MessageType
from genesis.domain.observability import decisions
from genesis.settings import settings

log = logging.getLogger(__name__)


class CampaignType(StrEnum):
    REACTIVATION = "reactivation"
    SEASONAL = "seasonal"
    REVIEW_REQUEST = "review_request"


MESSAGE_TYPE_OF = {
    CampaignType.REACTIVATION: MessageType.REACTIVATION,
    CampaignType.SEASONAL: MessageType.SEASONAL,
    CampaignType.REVIEW_REQUEST: MessageType.REVIEW_REQUEST,
}

# Audience rules. Each returns customers with the context its template needs.
AUDIENCE_SQL: dict[CampaignType, str] = {
    # Lapsed: served before, but not recently. Dormancy is derived from actual
    # service history, never from a flag someone set by hand.
    CampaignType.REACTIVATION: """
        select c.id, c.full_name,
               max(a.starts_at) as last_service_at,
               extract(day from now() - max(a.starts_at))::int as days_since
          from customers c
          join appointments a on a.customer_id = c.id and a.status = 'completed'
         where c.business_id = $1 and not c.do_not_contact
         group by c.id
        having max(a.starts_at) < now() - make_interval(days => $2)
         order by max(a.starts_at)
    """,
    # Everyone contactable. lapsed_days is irrelevant here, but every query in
    # this map takes the same two parameters so the caller stays uniform — the
    # explicit ::int cast is what tells Postgres how to type it.
    CampaignType.SEASONAL: """
        select c.id, c.full_name, null::timestamptz as last_service_at, 0 as days_since
          from customers c
         where c.business_id = $1 and not c.do_not_contact
           and $2::int >= 0
         order by c.full_name
    """,
    # Completed jobs that never got a review request answered.
    CampaignType.REVIEW_REQUEST: """
        select c.id, c.full_name,
               max(a.starts_at) as last_service_at,
               extract(day from now() - max(a.starts_at))::int as days_since
          from customers c
          join appointments a on a.customer_id = c.id and a.status = 'completed'
          left join reviews r on r.appointment_id = a.id and r.submitted_at is not null
         where c.business_id = $1 and not c.do_not_contact
           and r.id is null and $2::int >= 0
         group by c.id
         order by max(a.starts_at) desc
    """,
}


@dataclass(slots=True)
class Candidate:
    customer_id: str
    name: str
    eligible: bool
    reason: str | None
    code: str | None
    days_since: int


@dataclass(slots=True)
class Preview:
    campaign_type: str
    total: int
    eligible: int
    blocked: int
    candidates: list[Candidate]


async def preview(
    campaign_type: CampaignType, *, lapsed_days: int = 90
) -> Preview:
    """Run the Guard over the audience without sending anything."""
    message_type = MESSAGE_TYPE_OF[campaign_type]

    async with pool.connection() as conn:
        rows = await conn.fetch(
            AUDIENCE_SQL[campaign_type], settings.demo_business_id, lapsed_days
        )

        candidates: list[Candidate] = []
        for row in rows:
            verdict = await guard.evaluate(
                conn,
                business_id=settings.demo_business_id,
                customer_id=str(row["id"]),
                message_type=message_type,
                dedupe_key=None,
            )
            candidates.append(
                Candidate(
                    customer_id=str(row["id"]),
                    name=row["full_name"],
                    eligible=verdict.allowed,
                    reason=verdict.reason,
                    code=verdict.code.value if verdict.code else None,
                    days_since=int(row["days_since"] or 0),
                )
            )

    eligible = sum(1 for c in candidates if c.eligible)
    return Preview(
        campaign_type=campaign_type.value,
        total=len(candidates),
        eligible=eligible,
        blocked=len(candidates) - eligible,
        candidates=candidates,
    )


async def launch(
    *,
    name: str,
    campaign_type: CampaignType,
    customer_ids: list[str],
) -> dict:
    """Create the campaign and enqueue one job per recipient.

    Recipients are recorded for everyone selected, including those the Guard
    will refuse. A campaign that reports "sent to 12" when 9 were blocked is
    worse than useless, so the roll-up counts what actually happened.
    """
    if not customer_ids:
        raise ValueError("Select at least one recipient")

    message_type = MESSAGE_TYPE_OF[campaign_type]
    now = datetime.now(UTC)

    async with pool.transaction() as conn:
        campaign_id = await conn.fetchval(
            """
            insert into campaigns
              (business_id, name, campaign_type, status, template_key, started_at)
            values ($1, $2, $3, 'running', $4, $5)
            returning id
            """,
            settings.demo_business_id,
            name,
            campaign_type.value,
            message_type.value,
            now,
        )

        for customer_id in customer_ids:
            await conn.execute(
                """
                insert into campaign_recipients (business_id, campaign_id, customer_id)
                values ($1, $2, $3)
                on conflict (campaign_id, customer_id) do nothing
                """,
                settings.demo_business_id,
                campaign_id,
                customer_id,
            )
            await conn.execute(
                """
                insert into automation_jobs
                  (business_id, job_type, scheduled_for, payload, dedupe_key)
                values ($1, 'campaign_message', $2, $3::jsonb, $4)
                on conflict do nothing
                """,
                settings.demo_business_id,
                now,
                json.dumps(
                    {
                        "campaign_id": str(campaign_id),
                        "customer_id": customer_id,
                        "message_type": message_type.value,
                    }
                ),
                f"campaign:{campaign_id}:{customer_id}",
            )

        await decisions.record(
            business_id=settings.demo_business_id,
            event_type="campaign_launched",
            summary=f"Campaign '{name}' queued for {len(customer_ids)} customer(s)",
            detail={"campaign_id": str(campaign_id), "type": campaign_type.value},
            conn=conn,
        )

    return {"campaign_id": str(campaign_id), "queued": len(customer_ids)}


async def finalise_if_complete(campaign_id: str) -> None:
    """Mark a campaign completed once no recipient is still pending."""
    await pool.execute(
        """
        update campaigns set status = 'completed', completed_at = now()
         where id = $1
           and status = 'running'
           and not exists (
             select 1 from campaign_recipients
              where campaign_id = $1 and status = 'pending'
           )
        """,
        campaign_id,
    )
