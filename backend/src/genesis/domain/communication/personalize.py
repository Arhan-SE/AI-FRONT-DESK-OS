"""Personalised message copy.

Templates guarantee a message can always be produced. This produces a better
one when it can: gpt-4o-mini writes from the customer's actual history —
what they had done, when, by whom, what they owe — instead of substituting a
name into a fixed sentence.

Two rules make this safe to put in front of customers:

1. The model is given facts, never a database. It cannot look anything up, so
   it can only be wrong about what we handed it.
2. Failure is never fatal. Anything unexpected — a timeout, an empty response,
   a suspiciously long one — falls back to the template. A customer gets the
   plainer message rather than no message.
"""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from genesis.db import pool
from genesis.domain.communication.types import MessageType
from genesis.domain.observability import usage
from genesis.settings import settings

log = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI | None:
    global _client
    if not settings.ai_enabled:
        return None
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=12.0)
    return _client


SYSTEM = """You write short WhatsApp-style messages for an Indian home-services \
business (air conditioning). You are writing on behalf of the business owner.

Rules:
- 1 to 2 sentences. This is a phone notification, not an email.
- Warm and direct. Indian English. No corporate filler.
- Use ONLY the facts given to you. Never invent a date, price, name, offer or
  discount. If a fact is absent, write around it.
- Amounts in rupees, written as Rs 1,499.
- No markdown, no bullet points, no subject line, no signature block.
- Emoji are usually unnecessary. Use one only if the message reads coldly without it.
- Never claim the customer did something they did not do.
- Never assert that a date has passed unless you are told it has. A due date in
  the future is not overdue.
- End with the specific next step the business wants, if one is given.

Return only the message text."""


INTENT: dict[MessageType, str] = {
    MessageType.APPOINTMENT_CONFIRMATION:
        "Confirm the booking and tell them who is coming and when.",
    MessageType.APPOINTMENT_REMINDER:
        "Remind them about tomorrow's visit. Offer to reschedule if needed.",
    MessageType.POST_SERVICE_FOLLOWUP:
        "Check the work is holding up. Invite them to reply if anything is wrong.",
    MessageType.REVIEW_REQUEST:
        "Ask for a rating from 1 to 5, where 5 is excellent. Keep it light.",
    MessageType.INVOICE_SENT:
        "Send them the bill for work just completed. State the amount and when "
        "it is due. Friendly, not a demand — nothing is late yet.",
    MessageType.PAYMENT_REMINDER:
        "Politely remind them the invoice is unpaid. Do not be aggressive, "
        "even on a later reminder. Ask them to reply once it is settled.",
    MessageType.REACTIVATION:
        "It has been a while. Suggest a service, referencing what they had done "
        "before. Invite them to reply YES to book.",
    MessageType.SEASONAL:
        "Suggest booking ahead of the busy season. Reference their history if "
        "there is any. Invite them to reply YES.",
}


async def build_facts(
    customer_id: str, message_type: MessageType, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Gather what is true about this customer, from the database only."""
    row = await pool.fetchrow(
        """
        select c.full_name,
               (select count(*) from appointments a
                 where a.customer_id = c.id and a.status = 'completed') as jobs_completed,
               (select s.name from appointments a
                  join services s on s.id = a.service_id
                 where a.customer_id = c.id and a.status = 'completed'
                 order by a.starts_at desc limit 1) as last_service,
               (select a.starts_at from appointments a
                 where a.customer_id = c.id and a.status = 'completed'
                 order by a.starts_at desc limit 1) as last_service_at,
               (select t.full_name from appointments a
                  join technicians t on t.id = a.technician_id
                 where a.customer_id = c.id and a.status = 'completed'
                 order by a.starts_at desc limit 1) as last_technician
          from customers c
         where c.id = $1 and c.business_id = $2
        """,
        customer_id,
        settings.demo_business_id,
    )
    if row is None:
        return {}

    facts: dict[str, Any] = {
        "customer_first_name": row["full_name"].split()[0],
        "jobs_completed_with_us": row["jobs_completed"],
    }
    if row["last_service"]:
        facts["their_last_service"] = row["last_service"]
        facts["last_service_technician"] = row["last_technician"]
        facts["last_service_date"] = row["last_service_at"].astimezone(
            settings.tz
        ).strftime("%d %B %Y")
        months = int((pool_now() - row["last_service_at"]).days / 30)
        if months >= 1:
            facts["months_since_last_service"] = months

    facts.update(extra or {})
    # Drop empties so the model is never handed a blank to fill in.
    return {k: v for k, v in facts.items() if v not in (None, "", [])}


def pool_now():
    from datetime import UTC, datetime

    return datetime.now(UTC)


async def generate(message_type: MessageType, facts: dict[str, Any]) -> str | None:
    """Write the message. Returns None if the template should be used instead."""
    client = _get_client()
    if client is None or not facts:
        return None

    fact_lines = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in facts.items())
    prompt = (
        f"Goal: {INTENT[message_type]}\n\n"
        f"Business: Apex Climate Care, Bengaluru\n"
        f"Facts you may use:\n{fact_lines}"
    )

    try:
        response = await client.chat.completions.create(
            model=settings.reasoning_model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=160,
            temperature=0.6,
        )
        await usage.record_completion(response, purpose="personalisation")
        text = (response.choices[0].message.content or "").strip()
    except Exception:
        log.warning("personalisation failed for %s; using template", message_type, exc_info=True)
        return None

    # Guard against a model that ignored the brief. A 600-character "short
    # notification" is a failure even though the API call succeeded.
    if not text or len(text) > 480:
        log.warning("personalisation rejected for %s (len=%d)", message_type, len(text))
        return None

    return text
