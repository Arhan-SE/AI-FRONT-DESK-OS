"""Campaign endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel

from genesis.domain import campaigns

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


class CandidateModel(BaseModel):
    customer_id: str
    name: str
    eligible: bool
    reason: str | None
    code: str | None
    days_since: int


class PreviewResponse(BaseModel):
    campaign_type: str
    total: int
    eligible: int
    blocked: int
    candidates: list[CandidateModel]


class LaunchRequest(BaseModel):
    name: str
    campaign_type: campaigns.CampaignType
    customer_ids: list[str]


@router.get("/preview", response_model=PreviewResponse)
async def preview(
    campaign_type: campaigns.CampaignType,
    lapsed_days: int = 90,
) -> PreviewResponse:
    """Dry-run the Communication Guard over the audience.

    Nothing is sent and nothing is recorded — the Guard is a pure decision, so
    the owner can see exactly who would be refused, and why, before committing.
    """
    result = await campaigns.preview(campaign_type, lapsed_days=lapsed_days)
    return PreviewResponse(
        campaign_type=result.campaign_type,
        total=result.total,
        eligible=result.eligible,
        blocked=result.blocked,
        # asdict, not __dict__ — Candidate uses slots and has no instance dict.
        candidates=[CandidateModel(**asdict(c)) for c in result.candidates],
    )


@router.post("", status_code=201)
async def launch(body: LaunchRequest) -> dict:
    return await campaigns.launch(
        name=body.name,
        campaign_type=body.campaign_type,
        customer_ids=body.customer_ids,
    )
