"""Reset the demo tenant to a clean, honest starting state.

Configuration is kept — the business, its services, technicians, opening hours
and message templates. Activity is not: no invented customers, appointments,
invoices or reviews.

The dashboard therefore starts near-empty and fills up as the system is
demonstrated. A judge watching counters move while they press buttons is more
convincing than a dashboard that was already full when they arrived.

Run with:  uv run python -m genesis.db.seed
"""

from __future__ import annotations

import asyncio
import logging

from genesis.db import pool
from genesis.settings import settings

log = logging.getLogger(__name__)

BUSINESS_ID = settings.demo_business_id

# Real people who will use the system. Phone numbers are placeholders for voice
# identification and can be edited in the Customers page; telegram_chat_id is
# populated when each person messages the bot.
CUSTOMERS: list[tuple[str, str]] = [
    ("Muhammad Kareem", "+91 90000 00001"),
    ("Imran Sheik", "+91 90000 00002"),
    ("Mohammed Rafi", "+91 90000 00003"),
    ("Mohammed Sadiq", "+91 90000 00004"),
    ("Karthik R", "+91 90000 00005"),
]

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

        for name, phone in CUSTOMERS:
            await conn.execute(
                """
                insert into customers (business_id, full_name, phone, status)
                values ($1, $2, $3, 'active')
                """,
                BUSINESS_ID,
                name,
                phone,
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
    print("\nCustomers:")
    for name, phone in CUSTOMERS:
        print(f"  · {name:18} {phone}")
    print("\nNo Telegram chat ids yet — the Guard will block outreach until each")
    print("person messages the bot. That is correct behaviour, not a failure.")
    await pool.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
