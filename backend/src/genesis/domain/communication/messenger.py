"""send_customer_message — the one way anything reaches a customer.

Agent tools, automation jobs and campaigns all call this. None of them talk to
Telegram directly, which is what makes the frequency caps, duplicate prevention
and audit trail actual guarantees rather than conventions.

Every outcome is recorded, including refusals. A message the Guard blocked is
as interesting operationally as one that was sent — "why didn't my customer get
a reminder?" must be answerable from the database.
"""

from __future__ import annotations

import logging

from genesis.db import pool
from genesis.domain.communication import guard, personalize, telegram, templates
from genesis.domain.communication.types import (
    CATEGORY_OF,
    BlockCode,
    MessageType,
    SendResult,
)
from genesis.domain.observability import decisions

log = logging.getLogger(__name__)


async def send_customer_message(
    *,
    business_id: str,
    customer_id: str,
    message_type: MessageType,
    context: dict[str, object],
    dedupe_key: str | None = None,
    campaign_id: str | None = None,
    template_key: str | None = None,
) -> SendResult:
    category = CATEGORY_OF[message_type]
    key = template_key or message_type.value

    async with pool.connection() as conn:
        verdict = await guard.evaluate(
            conn,
            business_id=business_id,
            customer_id=customer_id,
            message_type=message_type,
            dedupe_key=dedupe_key,
        )

        # ---------------------------------------------------------- blocked
        if not verdict.allowed:
            log_id = await conn.fetchval(
                """
                insert into message_log
                  (business_id, customer_id, campaign_id, message_type, category,
                   channel, status, block_reason, dedupe_key)
                values ($1,$2,$3,$4,$5,'telegram','blocked',$6,$7)
                returning id
                """,
                business_id,
                customer_id,
                campaign_id,
                message_type.value,
                category.value,
                verdict.reason,
                dedupe_key,
            )
            await decisions.record(
                business_id=business_id,
                customer_id=customer_id,
                event_type="message_blocked",
                status="blocked",
                summary=f"{_label(message_type)} not sent — {verdict.reason}",
                detail={"code": verdict.code, "message_type": message_type.value},
                tool_name="send_customer_message",
                conn=conn,
            )
            return SendResult(
                sent=False,
                blocked=True,
                code=verdict.code,
                reason=verdict.reason,
                message_log_id=str(log_id),
            )

        chat_id = await conn.fetchval(
            "select telegram_chat_id from customers where id = $1", customer_id
        )

    # ------------------------------------------------------------- compose
    #
    # Personalised copy when the model can produce it, template otherwise.
    # The template is not a legacy path — it is the guarantee that a message
    # can always be produced, so a model outage degrades the wording rather
    # than dropping the message.
    facts = await personalize.build_facts(customer_id, message_type, extra=context)
    body = await personalize.generate(message_type, facts)
    personalised = body is not None

    if body is None:
        try:
            body = await templates.render_template(business_id, key, context)
        except templates.TemplateError as exc:
            await _record_failure(
                business_id, customer_id, campaign_id, message_type, dedupe_key, str(exc)
            )
            return SendResult(sent=False, blocked=False, code=None, reason=str(exc))

    # --------------------------------------------------------------- send
    delivery = await telegram.send_message(int(chat_id), body)

    async with pool.connection() as conn:
        if not delivery.ok:
            log_id = await conn.fetchval(
                """
                insert into message_log
                  (business_id, customer_id, campaign_id, message_type, category,
                   channel, body, status, error, dedupe_key)
                values ($1,$2,$3,$4,$5,'telegram',$6,'failed',$7,$8)
                returning id
                """,
                business_id, customer_id, campaign_id, message_type.value,
                category.value, body, delivery.error, dedupe_key,
            )

            # A blocked bot is permanent. Clearing the opt-in stops every future
            # job from retrying into the same wall.
            if delivery.unreachable:
                await conn.execute(
                    "update customers set telegram_opted_in = false where id = $1",
                    customer_id,
                )

            await decisions.record(
                business_id=business_id,
                customer_id=customer_id,
                event_type="message_failed",
                status="failure",
                summary=f"{_label(message_type)} failed to send",
                detail={"error": delivery.error},
                tool_name="send_customer_message",
                conn=conn,
            )
            return SendResult(
                sent=False, blocked=False, code=None,
                reason=delivery.error, message_log_id=str(log_id),
            )

        # ------------------------------------------------------------ sent
        log_id = await conn.fetchval(
            """
            insert into message_log
              (business_id, customer_id, campaign_id, message_type, category,
               channel, body, status, telegram_message_id, dedupe_key)
            values ($1,$2,$3,$4,$5,'telegram',$6,'sent',$7,$8)
            returning id
            """,
            business_id, customer_id, campaign_id, message_type.value,
            category.value, body, delivery.message_id, dedupe_key,
        )
        await conn.execute(
            "update customers set last_contacted_at = now() where id = $1", customer_id
        )
        await decisions.record(
            business_id=business_id,
            customer_id=customer_id,
            event_type="message_sent",
            summary=(
                f"{_label(message_type)} sent"
                + (" — personalised from service history" if personalised else "")
            ),
            detail={
                "message_type": message_type.value,
                "channel": "telegram",
                "personalised": personalised,
                "body": body,
            },
            tool_name="send_customer_message",
            conn=conn,
        )

    return SendResult(
        sent=True, blocked=False, code=None, reason=None,
        message_log_id=str(log_id), telegram_message_id=delivery.message_id,
    )


async def _record_failure(
    business_id: str,
    customer_id: str,
    campaign_id: str | None,
    message_type: MessageType,
    dedupe_key: str | None,
    error: str,
) -> None:
    await pool.execute(
        """
        insert into message_log
          (business_id, customer_id, campaign_id, message_type, category,
           channel, status, error, dedupe_key)
        values ($1,$2,$3,$4,$5,'telegram','failed',$6,$7)
        """,
        business_id, customer_id, campaign_id, message_type.value,
        CATEGORY_OF[message_type].value, error, dedupe_key,
    )
    log.error("message render failed type=%s: %s", message_type, error)


_LABELS: dict[MessageType, str] = {
    MessageType.APPOINTMENT_CONFIRMATION: "Booking confirmation",
    MessageType.APPOINTMENT_REMINDER: "Appointment reminder",
    MessageType.POST_SERVICE_FOLLOWUP: "Post-service follow-up",
    MessageType.PAYMENT_REMINDER: "Payment reminder",
    MessageType.REVIEW_REQUEST: "Review request",
    MessageType.REACTIVATION: "Reactivation message",
    MessageType.SEASONAL: "Seasonal campaign",
}


def _label(message_type: MessageType) -> str:
    return _LABELS.get(message_type, message_type.value)


__all__ = ["send_customer_message", "BlockCode", "MessageType", "SendResult"]
