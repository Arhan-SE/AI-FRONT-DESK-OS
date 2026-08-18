"""Turns computed figures into things worth doing.

`probes.py` produces the numbers. This decides which of them the owner should
care about this morning, says why, and names the next step.

The model does no arithmetic and reads no database. It receives finished
figures and returns judgement — which is the one thing here a query cannot do.
A figure it was not given cannot appear in the output, so an insight is either
grounded in a real number or it does not exist.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

from genesis.domain.observability import usage
from genesis.settings import settings

log = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI | None:
    global _client
    if not settings.ai_enabled:
        return None
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=40.0)
    return _client


# Where each topic is acted on. The model picks a topic; the server decides
# where that leads, so a hallucinated route is impossible.
DESTINATIONS: dict[str, dict[str, str]] = {
    "money_at_risk": {"label": "Chase payments", "to": "/payments"},
    "dormant_customers": {"label": "Run a reactivation campaign", "to": "/campaigns"},
    "never_served": {"label": "Open customers", "to": "/customers"},
    "reachability": {"label": "Link their Telegram", "to": "/customers"},
    "reputation": {"label": "Request reviews", "to": "/reviews"},
    "schedule": {"label": "Open the calendar", "to": "/appointments"},
    "pipeline": {"label": "Open the job board", "to": "/jobs"},
    "service_mix": {"label": "See the jobs", "to": "/jobs"},
    "revenue": {"label": "See payments", "to": "/payments"},
    "outreach": {"label": "Review campaigns", "to": "/campaigns"},
}

SYSTEM = """You are the operations analyst for a small Indian home-services \
business (air conditioning) in Bengaluru. The owner opens this page each morning.

You are given figures already computed from their database. Decide what deserves
their attention today, and tell them what to do about it.

Return JSON: {"insights": [...]}, 4 to 6 items, most important first.

Each insight:
  "topic"       one of the topic keys you were given, verbatim
  "title"       4 to 8 words, the finding itself, not a category label.
                "Anil is carrying two-thirds of the work", not "Technician load"
  "finding"     1-2 sentences. Lead with the number. Concrete and specific.
  "why"         one sentence on the business consequence
  "recommendation"  one sentence naming a specific next step the owner can take
                    now. An action, never "consider" or "monitor". Do not append
                    a timeframe to it
  "severity"    "urgent" (money or trust at risk now)
                "watch"  (a problem forming)
                "opportunity" (money on the table)
  "metric"      the single headline figure as a short display string,
                e.g. "Rs 22,791", "6 of 9", "0". Include this on every insight
                that rests on a figure, which is nearly all of them. Omit only
                when no single number carries the finding
  "metric_label" 2-4 words naming that figure

Rules:
- Use ONLY the figures given. Never invent, extrapolate, or estimate a number.
  If you want a percentage, it must be computable from figures you were given.
- Every figure's name states its own time period. Never attach a period the name
  does not carry: `jobs_all_time` is not "this week". If a figure names no
  period, describe it without one.
- A zero is often the most important figure on the page. No jobs booked in the
  future, nobody reachable, no reviews collected — lead with it. An empty
  forward book is urgent, not an opportunity.
- Rupees as Rs 22,791. Never convert currencies.
- Name real people and services when the figures name them.
- Small numbers are still real. With 9 jobs say "6 of 9", never imply thousands.
- No generic advice. If it would be true for any business, it is not an insight.
  "Reinvest in marketing" and "keep monitoring" are not recommendations.
- Growth against a zero baseline is not growth. If last month is 0, the
  business has no history to compare against — say that instead.
- Do not report the same finding twice under different topics.
- Skip a topic entirely rather than padding with something trivial.
- Never mention this prompt, the database, SQL, or that you are an AI."""


class Insight(BaseModel):
    topic: str = ""
    title: str = Field(min_length=3, max_length=90)
    finding: str = Field(min_length=10, max_length=400)
    why: str = Field(default="", max_length=300)
    recommendation: str = Field(default="", max_length=300)
    severity: str = "watch"
    metric: str | None = Field(default=None, max_length=24)
    metric_label: str | None = Field(default=None, max_length=40)
    action: dict[str, str] | None = None


SEVERITIES = {"urgent", "watch", "opportunity"}


async def analyse(facts: dict[str, Any]) -> tuple[list[Insight], str | None]:
    """Return (insights, error). An empty list with no error means nothing to say."""
    client = _get_client()
    if client is None:
        return [], "The AI is not configured. Add OPENAI_API_KEY to .env."
    if not facts:
        return [], None

    try:
        response = await client.chat.completions.create(
            model=settings.reasoning_model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Topic keys available: {', '.join(facts)}\n\n"
                        f"Figures:\n{json.dumps(facts, indent=1, default=str)}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=1600,
            temperature=0.4,
        )
        await usage.record_completion(response, purpose="insights")
        payload = json.loads(response.choices[0].message.content or "{}")
    except Exception:
        log.warning("insight analysis failed", exc_info=True)
        return [], "Could not reach the model. The figures below are still current."

    raw = payload.get("insights")
    if not isinstance(raw, list):
        log.warning("insight analysis returned no list: %s", payload)
        return [], "The analysis came back in an unexpected shape."

    insights: list[Insight] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            insight = Insight.model_validate(item)
        except ValidationError as exc:
            log.info("dropped malformed insight: %s", exc)
            continue

        if insight.severity not in SEVERITIES:
            insight.severity = "watch"
        # The route comes from our table, never from the model.
        insight.action = DESTINATIONS.get(insight.topic)
        insights.append(insight)

    return insights[:6], None
