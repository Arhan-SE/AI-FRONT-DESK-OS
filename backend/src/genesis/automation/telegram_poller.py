"""Inbound Telegram, over long polling.

Telegram never calls in — this dials out and asks for updates. That is what
lets the whole system run on localhost with no tunnel and no public URL. The
update-handling logic below is transport-agnostic, so a webhook could replace
the polling loop later without touching any of it.

What arrives here:
  "5"      -> a rating for the most recent review request
  "STOP"   -> marketing opt-out
  "YES"    -> interest in a campaign
  anything -> recorded against the conversation so the owner can read it
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from telegram import Update
from telegram.error import TelegramError

from genesis.db import pool
from genesis.domain.communication.telegram import get_bot
from genesis.domain.observability import decisions
from genesis.settings import settings

log = logging.getLogger("genesis.telegram")

RATING = re.compile(r"^\s*([1-5])\s*(?:/\s*5)?\s*$")
STOP_WORDS = {"stop", "unsubscribe", "opt out", "optout"}
YES_WORDS = {"yes", "y", "book", "interested", "ok", "okay"}

_offset: int | None = None


async def _find_customer(chat_id: int):
    return await pool.fetchrow(
        """
        select id, full_name, do_not_contact
          from customers
         where business_id = $1 and telegram_chat_id = $2
        """,
        settings.demo_business_id,
        chat_id,
    )


async def _record_unknown(chat_id: int, name: str, text: str) -> None:
    """Someone messaged the bot who is not linked to a customer.

    Recorded with the chat id visible, because that id is exactly what the
    owner needs to paste into the customer's record to make them contactable.
    Without this the only way to obtain it is a Telegram API call by hand.
    """
    await decisions.record(
        business_id=settings.demo_business_id,
        event_type="telegram_unlinked_message",
        status="pending",
        summary=f"Message from unlinked chat — {name} (chat id {chat_id})",
        detail={"chat_id": chat_id, "from": name, "text": text[:200]},
    )
    await pool.execute(
        """
        insert into notifications (business_id, title, body, severity)
        values ($1, $2, $3, 'warning')
        """,
        settings.demo_business_id,
        f"Unlinked Telegram message from {name}",
        f"Chat ID {chat_id} — open Customers and paste this into their record "
        f"to make them contactable. They said: “{text[:120]}”",
    )


async def _apply_rating(customer_id: str, customer_name: str, rating: int, text: str) -> bool:
    """Attach a rating to the most recent unanswered review request."""
    review = await pool.fetchrow(
        """
        update reviews
           set rating = $3, comment = $4, submitted_at = now()
         where id = (
           select id from reviews
            where business_id = $1 and customer_id = $2 and submitted_at is null
            order by requested_at desc nulls last
            limit 1
         )
        returning id, appointment_id
        """,
        settings.demo_business_id,
        customer_id,
        rating,
        text if len(text) > 1 else None,
    )
    if review is None:
        return False

    await decisions.record(
        business_id=settings.demo_business_id,
        customer_id=customer_id,
        event_type="review_received",
        summary=f"{customer_name} rated the service {rating}/5",
        detail={"rating": rating, "review_id": str(review["id"])},
    )
    return True


async def _handle_message(chat_id: int, sender: str, text: str) -> None:
    customer = await _find_customer(chat_id)

    if customer is None:
        await _record_unknown(chat_id, sender, text)
        return

    customer_id = str(customer["id"])
    name = customer["full_name"]
    lowered = text.strip().lower()

    # --- opt-out first: it must win over every other interpretation --------
    if lowered in STOP_WORDS:
        await pool.execute(
            "update customers set do_not_contact = true where id = $1", customer_id
        )
        await decisions.record(
            business_id=settings.demo_business_id,
            customer_id=customer_id,
            event_type="opted_out",
            status="blocked",
            summary=f"{name} opted out of messages",
        )
        bot = get_bot()
        if bot:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text="You've been unsubscribed. We won't send you offers again.",
                )
            except TelegramError:
                log.warning("could not confirm opt-out to %s", chat_id)
        return

    # --- a rating ---------------------------------------------------------
    match = RATING.match(text)
    if match and await _apply_rating(customer_id, name, int(match.group(1)), text):
        bot = get_bot()
        if bot:
            try:
                await bot.send_message(chat_id=chat_id, text="Thank you — noted.")
            except TelegramError:
                pass
        return

    # --- interest in a campaign -------------------------------------------
    if lowered in YES_WORDS:
        updated = await pool.fetchval(
            """
            with latest as (
              select id from campaign_recipients
               where business_id = $1 and customer_id = $2 and status = 'sent'
               order by sent_at desc limit 1
            )
            update campaign_recipients cr
               set status = 'replied', replied_at = now()
              from latest
             where cr.id = latest.id
            returning cr.campaign_id
            """,
            settings.demo_business_id,
            customer_id,
        )
        await pool.execute(
            """
            insert into tasks (business_id, customer_id, title, description,
                               task_type, priority)
            values ($1, $2, $3, $4, 'callback', 'high')
            """,
            settings.demo_business_id,
            customer_id,
            f"{name} wants to book",
            f"Replied “{text[:100]}” on Telegram.",
        )
        await decisions.record(
            business_id=settings.demo_business_id,
            customer_id=customer_id,
            event_type="campaign_reply",
            summary=f"{name} replied YES — callback task created",
            detail={"campaign_id": str(updated) if updated else None},
        )
        return

    # --- anything else ----------------------------------------------------
    await decisions.record(
        business_id=settings.demo_business_id,
        customer_id=customer_id,
        event_type="customer_replied",
        summary=f"{name} replied on Telegram",
        detail={"text": text[:200]},
    )


async def poll_once(timeout: int = 20) -> int:
    """Fetch and handle one batch. Returns how many updates were processed."""
    global _offset
    bot = get_bot()
    if bot is None:
        return 0

    try:
        updates: list[Update] = await bot.get_updates(
            offset=_offset, timeout=timeout, allowed_updates=["message"]
        )
    except TelegramError as exc:
        log.warning("getUpdates failed: %s", exc)
        return 0

    handled = 0
    for update in updates:
        # Advance past every update, even ones we ignore, or the same batch
        # arrives forever.
        _offset = update.update_id + 1

        message = update.message
        if message is None or not message.text:
            continue

        sender = message.from_user.full_name if message.from_user else "Unknown"
        try:
            await _handle_message(message.chat_id, sender, message.text)
            handled += 1
        except Exception:
            # One malformed message must not stop the poller.
            log.exception("failed handling update %s", update.update_id)

    return handled


async def run_forever(stop_event) -> None:
    bot = get_bot()
    if bot is None:
        log.warning("Telegram polling disabled — no bot token configured")
        return

    try:
        me = await bot.get_me()
        log.info("telegram poller started as @%s", me.username)
    except TelegramError as exc:
        log.error("could not reach Telegram: %s", exc)
        return

    while not stop_event.is_set():
        handled = await poll_once()
        if handled:
            log.info("handled %d inbound message(s)", handled)

    log.info("telegram poller stopped at %s", datetime.now(UTC).isoformat(timespec="seconds"))
