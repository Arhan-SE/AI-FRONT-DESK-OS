"""Token, minute and cost accounting.

Cost is calculated when the event is recorded and stored alongside it. Deriving
it on read would mean last month's bill changed every time a rate did, which is
the opposite of what an accounting figure is for.

Rates come from settings and are configuration rather than fact — see the note
there before quoting a number to anyone.
"""

from __future__ import annotations

import logging

from genesis.db import pool
from genesis.settings import settings

log = logging.getLogger(__name__)

PER_MILLION = 1_000_000


def realtime_cost(
    *,
    input_text: int,
    input_audio: int,
    input_cached: int,
    output_text: int,
    output_audio: int,
) -> float:
    # Cached input is billed separately and much cheaper, so it is subtracted
    # from the full-rate input rather than counted twice.
    uncached_text = max(0, input_text - input_cached)
    return (
        uncached_text * settings.rate_realtime_text_input
        + input_cached * settings.rate_realtime_cached_input
        + input_audio * settings.rate_realtime_audio_input
        + output_text * settings.rate_realtime_text_output
        + output_audio * settings.rate_realtime_audio_output
    ) / PER_MILLION


def text_cost(*, input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * settings.rate_mini_input
        + output_tokens * settings.rate_mini_output
    ) / PER_MILLION


async def record(
    *,
    source: str,
    model: str,
    purpose: str | None = None,
    conversation_id: str | None = None,
    input_text_tokens: int = 0,
    input_audio_tokens: int = 0,
    input_cached_tokens: int = 0,
    output_text_tokens: int = 0,
    output_audio_tokens: int = 0,
    duration_seconds: float = 0.0,
) -> None:
    """Record one billable interaction.

    Never raises. Accounting that can take down a customer conversation is
    worse than accounting that occasionally misses a row.
    """
    if source == "realtime":
        cost = realtime_cost(
            input_text=input_text_tokens,
            input_audio=input_audio_tokens,
            input_cached=input_cached_tokens,
            output_text=output_text_tokens,
            output_audio=output_audio_tokens,
        )
    elif source == "embedding":
        cost = input_text_tokens * settings.rate_embedding / PER_MILLION
    else:
        cost = text_cost(
            input_tokens=input_text_tokens, output_tokens=output_text_tokens
        )

    try:
        await pool.execute(
            """
            insert into usage_events
              (business_id, conversation_id, source, model, purpose,
               input_text_tokens, input_audio_tokens, input_cached_tokens,
               output_text_tokens, output_audio_tokens, duration_seconds, cost_usd)
            values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            """,
            settings.demo_business_id,
            conversation_id,
            source,
            model,
            purpose,
            input_text_tokens,
            input_audio_tokens,
            input_cached_tokens,
            output_text_tokens,
            output_audio_tokens,
            round(duration_seconds, 2),
            round(cost, 6),
        )
    except Exception:
        log.warning("could not record usage (%s/%s)", source, purpose, exc_info=True)


async def record_completion(response, *, purpose: str, conversation_id: str | None = None) -> None:
    """Record usage from an OpenAI chat completion response."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    await record(
        source="text",
        model=settings.reasoning_model,
        purpose=purpose,
        conversation_id=conversation_id,
        input_text_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_text_tokens=getattr(usage, "completion_tokens", 0) or 0,
    )
