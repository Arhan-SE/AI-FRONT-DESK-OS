"""Insights — what the owner should look at this morning.

Deterministic figures from `probes`, judgement from `analyst`. The figures are
returned alongside the insights so the page still has something true to show
when the model is unavailable.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from genesis.domain.insights import analyst, probes
from genesis.domain.observability import decisions
from genesis.settings import settings

router = APIRouter(prefix="/api/insights", tags=["insights"])


class InsightsResponse(BaseModel):
    insights: list[analyst.Insight]
    facts: dict[str, Any]
    generated_ms: int
    error: str | None = None


@router.get("", response_model=InsightsResponse)
async def get_insights() -> InsightsResponse:
    started = time.perf_counter()

    facts = await probes.gather(settings.demo_business_id)
    insights, error = await analyst.analyse(facts)
    elapsed = int((time.perf_counter() - started) * 1000)

    if insights:
        await decisions.record(
            business_id=settings.demo_business_id,
            event_type="insights_generated",
            summary=(
                f"Analysed {len(facts)} areas of the business — "
                f"{len(insights)} thing(s) worth attention"
            ),
            detail={
                "topics": list(facts),
                "titles": [i.title for i in insights],
                "urgent": sum(1 for i in insights if i.severity == "urgent"),
            },
            tool_name="insights",
            duration_ms=elapsed,
        )

    return InsightsResponse(
        insights=insights, facts=facts, generated_ms=elapsed, error=error
    )
