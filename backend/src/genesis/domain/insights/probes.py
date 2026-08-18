"""Deterministic analysis of the business.

Every number an insight rests on is computed here, in SQL, by hand. The model
never queries anything and never does arithmetic — it receives finished figures
and decides which of them matter and what the owner should do about them.

That split is the whole design. A model asked to "find insights in my data"
invents plausible numbers; a model handed `overdue_amount = 2999` and asked what
it means cannot. If a probe returns nothing, the model has nothing to say about
that topic, which is the correct outcome rather than a fabricated one.

Each probe is independent. One failing does not take the page down — it just
removes one topic from consideration.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any

from genesis.db import pool
from genesis.settings import settings

log = logging.getLogger(__name__)


def _num(value: Any) -> Any:
    """Decimals become floats so the figures survive JSON without losing money."""
    return float(value) if isinstance(value, Decimal) else value


def _rows(records: list) -> list[dict]:
    return [{k: _num(v) for k, v in r.items()} for r in records]


# --------------------------------------------------------------------------
# Probes
#
# Each returns a dict of finished figures, or {} when there is nothing to say.
# Keys are written to be readable by the model without a schema.
# --------------------------------------------------------------------------


async def revenue(bid: str) -> dict:
    """This month against last, and what a job is worth on average."""
    row = await pool.fetchrow(
        """
        select
          coalesce(sum(amount) filter (
            where date_trunc('month', paid_at) = date_trunc('month', current_date)
          ), 0) as collected_this_month,
          coalesce(sum(amount) filter (
            where date_trunc('month', paid_at)
                = date_trunc('month', current_date - interval '1 month')
          ), 0) as collected_last_month,
          coalesce(round(avg(amount) filter (where status = 'paid'), 0), 0) as average_job_value,
          count(*) filter (where status = 'paid') as invoices_paid
          from invoices
         where business_id = $1
        """,
        bid,
    )
    return {k: _num(v) for k, v in row.items()} if row else {}


async def money_at_risk(bid: str) -> dict:
    """Unpaid invoices, and how long they have been unpaid."""
    row = await pool.fetchrow(
        """
        select
          count(*) filter (where status in ('sent', 'overdue'))            as unpaid_invoices,
          coalesce(sum(amount) filter (where status in ('sent','overdue')), 0) as unpaid_total,
          count(*) filter (where status in ('sent','overdue')
                             and due_on < current_date)                    as overdue_invoices,
          coalesce(sum(amount) filter (where status in ('sent','overdue')
                             and due_on < current_date), 0)                as overdue_total,
          max(current_date - due_on) filter (where status in ('sent','overdue')
                             and due_on < current_date)                    as oldest_overdue_days
          from invoices
         where business_id = $1
        """,
        bid,
    )
    if not row or row["unpaid_invoices"] == 0:
        return {}

    who = await pool.fetch(
        """
        select customer_name, amount, (current_date - due_on) as days_overdue
          from v_invoices
         where business_id = $1 and status in ('sent','overdue')
         order by due_on
         limit 5
        """,
        bid,
    )
    return {**{k: _num(v) for k, v in row.items()}, "unpaid_customers": _rows(who)}


async def dormant(bid: str) -> dict:
    """Customers who have gone quiet, and what they used to be worth."""
    rows = await pool.fetch(
        """
        select full_name,
               (current_date - last_service_at::date) as days_since_service,
               total_paid,
               jobs_completed,
               reachable
          from v_customers
         where business_id = $1
           and last_service_at is not null
           and last_service_at < now() - interval '60 days'
         order by total_paid desc
         limit 8
        """,
        bid,
    )
    if not rows:
        return {}
    return {
        "dormant_count": len(rows),
        "dormant_lifetime_value": round(sum(float(r["total_paid"]) for r in rows), 2),
        "dormant_customers": _rows(rows),
    }


async def never_served(bid: str) -> dict:
    """On the books, never bought. The cheapest revenue in the business."""
    rows = await pool.fetch(
        """
        select full_name, reachable, (current_date - created_at::date) as days_on_books
          from v_customers
         where business_id = $1 and jobs_completed = 0 and jobs_upcoming = 0
         order by created_at
         limit 8
        """,
        bid,
    )
    return {"never_served_count": len(rows), "never_served": _rows(rows)} if rows else {}


async def reachability(bid: str) -> dict:
    """Who cannot be reached at all. An unreachable customer is unmarketable."""
    row = await pool.fetchrow(
        """
        select count(*) as total_customers,
               count(*) filter (where reachable)      as reachable_customers,
               count(*) filter (where do_not_contact) as opted_out
          from v_customers
         where business_id = $1
        """,
        bid,
    )
    if not row or row["total_customers"] == 0:
        return {}
    unreachable = await pool.fetch(
        """select full_name, total_paid from v_customers
            where business_id = $1 and not reachable and not do_not_contact
            order by total_paid desc limit 6""",
        bid,
    )
    return {
        **{k: _num(v) for k, v in row.items()},
        "unreachable_customers": _rows(unreachable),
    }


async def schedule_load(bid: str) -> dict:
    """Where the work actually sits: by technician, and by day of week."""
    techs = await pool.fetch(
        """
        select technician_name,
               count(*)                                            as jobs_all_time,
               count(*) filter (where stage = 'cancelled')          as cancelled_all_time
          from v_jobs
         where business_id = $1 and technician_name is not null
         group by technician_name
         order by jobs_all_time desc
        """,
        bid,
    )
    days = await pool.fetch(
        """
        select trim(to_char(starts_at, 'Day')) as weekday,
               count(*) as jobs_all_time
          from v_jobs
         where business_id = $1 and stage <> 'cancelled'
         group by 1 order by 2 desc
        """,
        bid,
    )
    upcoming = await pool.fetchval(
        """select count(*) from v_jobs
            where business_id = $1 and starts_at > now()
              and stage in ('scheduled','confirmed')""",
        bid,
    )
    if not techs:
        return {}
    return {
        "jobs_by_technician_all_time": _rows(techs),
        "jobs_by_weekday_all_time": _rows(days),
        "jobs_booked_in_the_future": _num(upcoming),
    }


async def service_mix(bid: str) -> dict:
    """Which services earn, and which merely keep everyone busy."""
    rows = await pool.fetch(
        """
        select service_name,
               count(*)                              as times_sold_all_time,
               coalesce(sum(invoice_amount), 0)      as revenue_all_time,
               coalesce(round(avg(service_price), 0), 0) as list_price
          from v_jobs
         where business_id = $1 and service_name is not null and stage <> 'cancelled'
         group by service_name
         order by revenue_all_time desc
        """,
        bid,
    )
    return {"services": _rows(rows)} if rows else {}


async def reputation(bid: str) -> dict:
    """Reviews collected against jobs finished — the gap is the opportunity."""
    row = await pool.fetchrow(
        """
        select
          (select count(*) from appointments
            where business_id = $1 and status = 'completed')          as jobs_completed,
          (select count(*) from reviews
            where business_id = $1 and rating is not null)            as reviews_with_rating,
          (select round(avg(rating)::numeric, 2) from reviews
            where business_id = $1 and rating is not null)            as average_rating,
          (select count(*) from reviews
            where business_id = $1 and rating is null)                as review_requests_unanswered
        """,
        bid,
    )
    return {k: _num(v) for k, v in row.items()} if row else {}


async def outreach_health(bid: str) -> dict:
    """What the Communication Guard stopped, and why. Blocks are diagnostics."""
    sent = await pool.fetchrow(
        """
        select count(*) filter (where status = 'sent')    as messages_sent,
               count(*) filter (where status = 'blocked') as messages_blocked,
               count(*) filter (where status = 'failed')  as messages_failed
          from message_log
         where business_id = $1 and created_at > now() - interval '30 days'
        """,
        bid,
    )
    reasons = await pool.fetch(
        """
        select block_reason, count(*) as times
          from message_log
         where business_id = $1 and status = 'blocked' and block_reason is not null
           and created_at > now() - interval '30 days'
         group by 1 order by 2 desc limit 5
        """,
        bid,
    )
    if not sent or sent["messages_sent"] == 0 and sent["messages_blocked"] == 0:
        return {}
    return {
        **{k: _num(v) for k, v in sent.items()},
        "block_reasons": _rows(reasons),
    }


async def pipeline_stalls(bid: str) -> dict:
    """Work that has stopped moving. Finished but unbilled is the expensive one."""
    rows = await pool.fetch(
        """
        select customer_name, service_name, stage,
               (current_date - completed_at::date) as days_since_completed,
               invoice_status
          from v_jobs
         where business_id = $1
           and stage = 'completed'
           and invoice_id is null
           and completed_at is not null
         order by completed_at
         limit 6
        """,
        bid,
    )
    upcoming_unconfirmed = await pool.fetchval(
        """select count(*) from v_jobs
            where business_id = $1 and stage = 'scheduled' and starts_at > now()""",
        bid,
    )
    out: dict[str, Any] = {"unconfirmed_upcoming_jobs": _num(upcoming_unconfirmed)}
    if rows:
        out["completed_but_not_invoiced"] = _rows(rows)
    return out


PROBES = {
    "revenue": revenue,
    "money_at_risk": money_at_risk,
    "dormant_customers": dormant,
    "never_served": never_served,
    "reachability": reachability,
    "schedule": schedule_load,
    "service_mix": service_mix,
    "reputation": reputation,
    "outreach": outreach_health,
    "pipeline": pipeline_stalls,
}


async def gather(business_id: str | None = None) -> dict[str, Any]:
    """Run every probe concurrently. A probe that fails is left out, not fatal."""
    bid = business_id or settings.demo_business_id
    names = list(PROBES)
    results = await asyncio.gather(
        *(PROBES[n](bid) for n in names), return_exceptions=True
    )

    facts: dict[str, Any] = {}
    for name, result in zip(names, results, strict=True):
        if isinstance(result, BaseException):
            log.warning("insight probe '%s' failed: %s", name, result)
            continue
        if result:
            facts[name] = result
    return facts
