"""Voice session endpoint.

Mints a short-lived LiveKit token for the browser. The token is the only thing
the frontend needs — it never sees the API secret, which stays on the server.

The token also carries who is calling. On a real phone line the caller's number
arrives with the call and the business looks them up before anyone speaks; there
is no number in a browser, so the caller is chosen from a list instead. From the
agent's side the two are identical: it is told who is on the line, or it is told
nothing and has to ask.

The identity is resolved here, server-side, from an id the browser cannot forge
into someone else's record — the customer must exist and belong to this
business. The browser never supplies the name the agent will use.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

from fastapi import APIRouter
from livekit import api
from pydantic import BaseModel

from genesis.db import pool
from genesis.settings import settings

router = APIRouter(prefix="/api/voice", tags=["voice"])


class SessionRequest(BaseModel):
    """Which customer is calling. Omitted or null means an unknown number."""

    customer_id: str | None = None


class SessionResponse(BaseModel):
    url: str
    token: str
    room: str
    identity: str
    caller_name: str | None = None


@router.post("/session", response_model=SessionResponse)
async def create_session(body: SessionRequest | None = None) -> SessionResponse:
    caller: dict[str, str] | None = None

    if body is not None and body.customer_id:
        row = await pool.fetchrow(
            """select id, full_name, phone from customers
                where id = $1 and business_id = $2""",
            body.customer_id,
            settings.demo_business_id,
        )
        if row is None:
            raise ValueError("Unknown customer")
        caller = {
            "customer_id": str(row["id"]),
            "full_name": row["full_name"],
            "phone": row["phone"] or "",
        }

    room = f"call-{uuid.uuid4().hex[:10]}"
    identity = f"caller-{uuid.uuid4().hex[:8]}"

    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(caller["full_name"] if caller else "Unknown caller")
        # Travels with the participant, so the agent knows who joined before
        # the first word is spoken.
        .with_metadata(json.dumps(caller) if caller else "")
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
        url=settings.livekit_url,
        token=token,
        room=room,
        identity=identity,
        caller_name=caller["full_name"] if caller else None,
    )
