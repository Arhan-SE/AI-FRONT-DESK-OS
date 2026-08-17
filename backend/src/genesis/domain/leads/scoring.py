"""Lead qualification.

The agent extracts; the backend decides. Scoring lives here rather than in the
model so it is deterministic, testable, and identical whether a lead arrives by
voice, by message, or by hand — and so the reasoning shown on the Leads page is
the actual reason, not a plausible-sounding sentence generated after the fact.

Five dimensions, weighted to 100. Weights are data, not code, so a business
that cares more about job value than location can be re-tuned without a
release.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from genesis.db import pool
from genesis.settings import settings

log = logging.getLogger(__name__)

WEIGHTS = {
    "intent": 25,
    "urgency": 20,
    "service_value": 20,
    "location": 20,
    "history": 15,
}

# Areas the business actually covers. A lead outside these is not worthless —
# it is a longer drive, and the score should say so rather than hide it.
SERVICE_AREAS = {
    "indiranagar", "koramangala", "whitefield", "hsr layout", "hsr",
    "jayanagar", "malleshwaram", "electronic city", "banashankari",
    "hebbal", "btm layout", "btm", "rajajinagar", "basavanagudi",
    "yelahanka", "marathahalli", "jp nagar", "vijayanagar", "bellandur",
    "kalyan nagar", "domlur", "ulsoor", "frazer town", "richmond town",
}

CITY_WORDS = {"bengaluru", "bangalore", "blr"}


@dataclass(slots=True)
class Score:
    score: int
    classification: str
    confidence: float
    factors: dict[str, int]
    reasoning: list[str] = field(default_factory=list)


def _location_points(location: str | None) -> tuple[int, str]:
    if not location:
        return 8, "Location not given"

    text = location.strip().lower()
    for area in SERVICE_AREAS:
        if area in text:
            return WEIGHTS["location"], f"{location.strip()} is in the service area"
    if any(city in text for city in CITY_WORDS):
        return 13, "Within the city but outside the usual areas"
    return 5, f"{location.strip()} looks outside the service area"


def _urgency_points(urgency: str | None) -> tuple[int, str]:
    return {
        "high": (WEIGHTS["urgency"], "Needs attention urgently"),
        "medium": (12, "Wants it done soon"),
        "low": (6, "No particular hurry"),
    }.get((urgency or "").lower(), (10, "Urgency not stated"))


def _service_points(price: float | None, matched: bool) -> tuple[int, str]:
    if not matched:
        return 0, "Not a service we offer"
    if price is None:
        return 10, "Service matched"
    # Scaled against the top of the price list rather than an absolute figure,
    # so the weighting still holds if prices change.
    if price >= 4000:
        return WEIGHTS["service_value"], "High-value job"
    if price >= 2000:
        return 14, "Mid-value job"
    return 9, "Lower-value job"


async def score_lead(
    *,
    service_id: str | None,
    location: str | None,
    urgency: str | None = None,
    customer_id: str | None = None,
    booked: bool = False,
) -> Score:
    factors: dict[str, int] = {}
    reasoning: list[str] = []

    # --- intent: did they actually commit to anything? --------------------
    if booked:
        factors["intent"] = WEIGHTS["intent"]
        reasoning.append("Booked an appointment on the call")
    elif service_id:
        factors["intent"] = 16
        reasoning.append("Asked about a specific service")
    else:
        factors["intent"] = 6
        reasoning.append("General enquiry, no service named")

    # --- service value ----------------------------------------------------
    price = None
    matched = service_id is not None
    if service_id:
        price = await pool.fetchval(
            "select base_price from services where id = $1 and business_id = $2",
            service_id,
            settings.demo_business_id,
        )
        price = float(price) if price is not None else None
    points, reason = _service_points(price, matched)
    factors["service_value"] = points
    reasoning.append(reason)

    # --- location ---------------------------------------------------------
    points, reason = _location_points(location)
    factors["location"] = points
    reasoning.append(reason)

    # --- urgency ----------------------------------------------------------
    points, reason = _urgency_points(urgency)
    factors["urgency"] = points
    reasoning.append(reason)

    # --- history ----------------------------------------------------------
    completed = 0
    if customer_id:
        completed = await pool.fetchval(
            """select count(*) from appointments
                where customer_id = $1 and status = 'completed'""",
            customer_id,
        ) or 0
    if completed >= 3:
        factors["history"] = WEIGHTS["history"]
        reasoning.append(f"Regular customer — {completed} previous jobs")
    elif completed >= 1:
        factors["history"] = 10
        reasoning.append(f"Returning customer — {completed} previous job(s)")
    else:
        factors["history"] = 4
        reasoning.append("First time customer")

    total = sum(factors.values())

    if total >= settings.hot_threshold:
        classification = "HOT"
    elif total >= settings.warm_threshold:
        classification = "WARM"
    else:
        classification = "COLD"

    # Confidence reflects how much we actually know, not how high the score is.
    known = sum(1 for v in (service_id, location, urgency, customer_id) if v)
    confidence = round(0.55 + 0.1 * known, 2)

    return Score(
        score=min(100, total),
        classification=classification,
        confidence=min(confidence, 0.95),
        factors=factors,
        reasoning=reasoning,
    )


async def upsert_lead(
    *,
    conversation_id: str | None,
    customer_id: str | None,
    service_id: str | None,
    service_name: str | None,
    location: str | None,
    urgency: str | None = None,
    preferred_timing: str | None = None,
    booked: bool = False,
) -> tuple[str, Score]:
    """Create or update the lead for this conversation, and score it.

    One lead per conversation: a caller who asks about two services is one
    lead, not two, and rescoring as the call develops is the point.
    """
    score = await score_lead(
        service_id=service_id,
        location=location,
        urgency=urgency,
        customer_id=customer_id,
        booked=booked,
    )

    async with pool.transaction() as conn:
        lead_id = None
        if conversation_id:
            lead_id = await conn.fetchval(
                "select id from leads where conversation_id = $1", conversation_id
            )

        if lead_id is None:
            lead_id = await conn.fetchval(
                """
                insert into leads
                  (business_id, customer_id, conversation_id, service_id, status,
                   source, urgency, requested_service, location, preferred_timing,
                   next_action)
                values ($1,$2,$3,$4,$5,'voice',$6,$7,$8,$9,$10)
                returning id
                """,
                settings.demo_business_id,
                customer_id,
                conversation_id,
                service_id,
                "converted" if booked else "qualified",
                urgency,
                service_name,
                location,
                preferred_timing,
                "Appointment booked" if booked else "Call back to confirm a slot",
            )
        else:
            await conn.execute(
                """
                update leads
                   set customer_id = coalesce($2, customer_id),
                       service_id = coalesce($3, service_id),
                       requested_service = coalesce($4, requested_service),
                       location = coalesce($5, location),
                       urgency = coalesce($6, urgency),
                       preferred_timing = coalesce($7, preferred_timing),
                       status = case when $8 then 'converted' else status end,
                       next_action = case when $8 then 'Appointment booked'
                                          else next_action end
                 where id = $1
                """,
                lead_id,
                customer_id,
                service_id,
                service_name,
                location,
                urgency,
                preferred_timing,
                booked,
            )

        # Scores are append-only, so the Leads detail view can show how the
        # assessment moved rather than only where it landed.
        await conn.execute(
            """
            insert into lead_scores
              (business_id, lead_id, score, classification, confidence, factors, reasoning)
            values ($1,$2,$3,$4,$5,$6::jsonb,$7)
            """,
            settings.demo_business_id,
            lead_id,
            score.score,
            score.classification,
            score.confidence,
            json.dumps(score.factors),
            score.reasoning,
        )

    return str(lead_id), score
