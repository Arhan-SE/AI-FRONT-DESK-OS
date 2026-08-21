"""Reset the tenant to a clean starting state.

Configuration is kept — the business, its services, technicians, opening hours
and message templates. Activity is not: no customers, appointments, invoices
or reviews.

You start with an empty book and fill it yourself, through the interface or by
talking to the voice agent. Nothing here invents people or history, so every
number on the dashboard is one you produced.

Run with:  uv run python -m genesis.db.seed
"""

from __future__ import annotations

import asyncio
import logging

from genesis.db import pool
from genesis.settings import settings

log = logging.getLogger(__name__)

BUSINESS_ID = settings.demo_business_id

# Order matters: children before parents. Several tables use ON DELETE SET NULL
# rather than CASCADE, so relying on the customer delete alone would leave
# orphaned leads and conversations behind.
WIPE_ORDER = [
    "ai_decisions",
    "messages",
    "conversations",
    "lead_scores",
    "leads",
    "message_log",
    "campaign_recipients",
    "campaigns",
    "automation_jobs",
    "tasks",
    "notifications",
    "audit_logs",
    "payments",
    "invoices",
    "reviews",
    "slot_holds",
    "appointments",
    "customer_memory",
    "customer_preferences",
    "customers",
]


async def reset() -> dict[str, int]:
    async with pool.transaction() as conn:
        for table in WIPE_ORDER:
            await conn.execute(
                f"delete from {table} where business_id = $1", BUSINESS_ID  # noqa: S608
            )

        counts = {
            "customers": await conn.fetchval(
                "select count(*) from customers where business_id = $1", BUSINESS_ID
            ),
            "services": await conn.fetchval(
                "select count(*) from services where business_id = $1", BUSINESS_ID
            ),
            "technicians": await conn.fetchval(
                "select count(*) from technicians where business_id = $1", BUSINESS_ID
            ),
            "templates": await conn.fetchval(
                "select count(*) from message_templates where business_id = $1", BUSINESS_ID
            ),
            "appointments": await conn.fetchval(
                "select count(*) from appointments where business_id = $1", BUSINESS_ID
            ),
        }
        return counts


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    counts = await reset()
    print("Reset complete — configuration kept, activity cleared.\n")
    for key, value in counts.items():
        print(f"  {key:14} {value}")
    print("\nAdd your first customer in the Customers page, or start a voice call")
    print("and let the agent create one. Outreach stays blocked by the Guard until")
    print("a customer messages the Telegram bot — that is correct, not a failure.")
    await pool.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
