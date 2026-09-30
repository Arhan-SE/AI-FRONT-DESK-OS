"""Outbound call endpoint.

There is no telephony and nothing goes out over Telegram. The owner clicks a
button in the dashboard, the browser navigates to /call/:purpose/:ref, and
that page resolves this endpoint into a LiveKit session — the same voice
agent as an inbound call, just briefed on why it's calling before anyone
picks up.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException
from livekit import api as lk_api
from pydantic import BaseModel

from genesis.domain.communication import outbound_calls as calls
from genesis.settings import settings

router = APIRouter(prefix="/api/calls", tags=["calls"])


class JoinRequest(BaseModel):
    purpose: calls.CallPurpose
    ref: str


class JoinResponse(BaseModel):
    url: str
    token: str
    room: str
    identity: str
    customer_name: str
    purpose: str
    # Purpose-specific facts (service, invoice amount, months since last
    # visit, ...) — shown on the call page so whoever is on it can follow
    # along with what the agent is about to say.
    facts: dict[str, object]


@router.post("/join", response_model=JoinResponse)
async def join_call(body: JoinRequest) -> JoinResponse:
    context = await calls.resolve_call_context(body.purpose, body.ref)
    if context is None:
        raise HTTPException(status_code=404, detail="This call could not be started")

    room = f"call-{body.purpose.value}-{uuid.uuid4().hex[:10]}"
    identity = f"caller-{uuid.uuid4().hex[:8]}"

    # Room metadata carries the call's purpose and facts to the agent — set
    # here, server-side, before anyone connects. The agent trusts this the
    # same way it trusts anything else read straight from the database,
    # because it came from the same place.
    async with lk_api.LiveKitAPI(
        settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret
    ) as lkapi:
        await lkapi.room.create_room(
            lk_api.CreateRoomRequest(name=room, metadata=json.dumps(context))
        )

    token = (
        lk_api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(context["customer_name"])
        .with_ttl(timedelta(minutes=15))
        .with_grants(
            lk_api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )

    facts = {k: v for k, v in context.items() if k not in ("purpose", "customer_id")}

    return JoinResponse(
        url=settings.livekit_url,
        token=token,
        room=room,
        identity=identity,
        customer_name=context["customer_name"],
        purpose=body.purpose.value,
        facts=facts,
    )
