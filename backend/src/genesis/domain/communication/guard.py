"""The Communication Guard.

Every automated message — from the agent, from a job, from a campaign — passes
through here. There is no bypass, because the moment one caller is allowed to
skip it, the frequency caps and duplicate-prevention stop being guarantees and
become suggestions.

The Guard only ever decides. It does not send, and it does not log; the
messenger does both, so that a blocked message and a sent message are recorded
through the same path and the UI can show why something was not sent.
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg

from genesis.domain.communication.types import (
    CATEGORY_OF,
    BlockCode,
    Category,
    GuardVerdict,
    MessageType,
)
from genesis.settings import settings


async def evaluate(
    conn: asyncpg.Connection,
    *,
    business_id: str,
    customer_id: str,
    message_type: MessageType,
    dedupe_key: str | None,
    now: datetime | None = None,
) -> GuardVerdict:
    now = now or datetime.now(UTC)
    category = CATEGORY_OF[message_type]

    # 0. Is there a channel at all? Checked first because every other check is
    #    pointless without one, and this is the honest answer during setup.
    if not settings.telegram_enabled:
        return GuardVerdict.block(
            BlockCode.NO_CHANNEL_CONFIGURED,
            "No Telegram bot token is configured",
        )

    customer = await conn.fetchrow(
        """
        select id, full_name, telegram_chat_id, telegram_opted_in,
               do_not_contact, last_contacted_at
          from customers
         where id = $1 and business_id = $2
        """,
        customer_id,
        business_id,
    )

    # 1. Identity.
    if customer is None:
        return GuardVerdict.block(
            BlockCode.CUSTOMER_NOT_FOUND, "Customer does not exist in this business"
        )

    # 2. Do-not-contact overrides everything, including transactional.
    if customer["do_not_contact"]:
        return GuardVerdict.block(
            BlockCode.DO_NOT_CONTACT, "Customer has opted out of all contact"
        )

    # 3. Reachability. Telegram cannot address a phone number — a customer is
    #    only reachable after they have started a chat with the bot. Missing
    #    chat id is a hard block, not a retryable error.
    if customer["telegram_chat_id"] is None:
        return GuardVerdict.block(
            BlockCode.NO_TELEGRAM_CHAT,
            "Customer has not linked Telegram (no chat id)",
        )

    if not customer["telegram_opted_in"]:
        return GuardVerdict.block(
            BlockCode.NOT_OPTED_IN, "Customer has not opted in to messaging"
        )

    # 4. Duplicate prevention. The unique index on message_log is the real
    #    enforcement — this check just avoids a pointless send attempt and
    #    gives a clean reason instead of a constraint error.
    if dedupe_key is not None:
        already = await conn.fetchval(
            """
            select 1 from message_log
             where business_id = $1 and message_type = $2
               and dedupe_key = $3 and status = 'sent'
             limit 1
            """,
            business_id,
            message_type.value,
            dedupe_key,
        )
        if already:
            return GuardVerdict.block(
                BlockCode.DUPLICATE, "This exact message has already been sent"
            )

    # -- Transactional messages stop here. ---------------------------------
    #
    # The customer earned these by booking a job or owing an invoice.
    # Suppressing a confirmation because of a marketing frequency cap would be
    # a bug, not a courtesy.
    if category is Category.TRANSACTIONAL:
        return GuardVerdict.allow()

    # -- Marketing only below. ---------------------------------------------

    # 5. Quiet hours, in the business's timezone, never the server's.
    local_hour = now.astimezone(settings.tz).hour
    start, end = settings.quiet_hours_start, settings.quiet_hours_end
    in_quiet = local_hour >= start or local_hour < end
    if in_quiet:
        return GuardVerdict.block(
            BlockCode.QUIET_HOURS,
            f"Quiet hours ({start}:00–{end}:00 {settings.business_timezone})",
        )

    # 6. Cooldown since the last marketing message.
    last_marketing = await conn.fetchval(
        """
        select max(created_at) from message_log
         where business_id = $1 and customer_id = $2
           and category = 'marketing' and status = 'sent'
        """,
        business_id,
        customer_id,
    )
    if last_marketing is not None:
        days = (now - last_marketing).total_seconds() / 86400
        if days < settings.marketing_cooldown_days:
            return GuardVerdict.block(
                BlockCode.COOLDOWN,
                f"Last marketing message was {days:.0f} days ago "
                f"(cooldown {settings.marketing_cooldown_days} days)",
            )

    # 7. Monthly cap.
    sent_this_month = await conn.fetchval(
        """
        select count(*) from message_log
         where business_id = $1 and customer_id = $2
           and category = 'marketing' and status = 'sent'
           and created_at >= date_trunc('month', now())
        """,
        business_id,
        customer_id,
    )
    if sent_this_month >= settings.max_marketing_per_month:
        return GuardVerdict.block(
            BlockCode.MONTHLY_CAP,
            f"Monthly marketing cap reached ({settings.max_marketing_per_month})",
        )

    return GuardVerdict.allow()
