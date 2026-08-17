"""Voice session endpoint.

Mints a short-lived LiveKit token for the browser. The token is the only thing
the frontend needs — it never sees the API secret, which stays on the server.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter
from livekit import api
from pydantic import BaseModel

from genesis.settings import settings

router = APIRouter(prefix="/api/voice", tags=["voice"])


class SessionResponse(BaseModel):
    url: str
    token: str
    room: str
    identity: str


@router.post("/session", response_model=SessionResponse)
async def create_session() -> SessionResponse:
    room = f"call-{uuid.uuid4().hex[:10]}"
    identity = f"caller-{uuid.uuid4().hex[:8]}"

    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name("Customer")
        # Short TTL: this grants entry to a room, and a leaked long-lived token
        # would let anyone join a call.
        .with_ttl(timedelta(minutes=15))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )

    return SessionResponse(
        url=settings.livekit_url, token=token, room=room, identity=identity
    )
