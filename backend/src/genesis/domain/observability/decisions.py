"""Writes the AI Activity feed.

Every observable action the system takes lands here, and the browser sees it
over Supabase Realtime within milliseconds. This is deliberately a record of
*what was decided*, never of how — no chain-of-thought, no prompts, no raw model
output. A short user-safe sentence and structured detail.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from genesis.db import pool

log = logging.getLogger(__name__)


async def record(
    *,
    business_id: str,
    event_type: str,
    summary: str,
    status: str = "success",
    conversation_id: str | None = None,
    customer_id: str | None = None,
    detail: dict[str, Any] | None = None,
    confidence: float | None = None,
    tool_name: str | None = None,
    duration_ms: int | None = None,
    conn: asyncpg.Connection | None = None,
) -> str | None:
    """Record one decision.

    Observability must never take the system down: if this write fails, the
    caller's actual work should still stand.

    Swallowing the exception is not enough to achieve that. Inside an open
    transaction a failed statement aborts the whole transaction, so catching
    the error here would leave the caller committing nothing — a failed audit
    row would silently undo the booking it was describing. The insert therefore
    runs inside a savepoint, which is what confines the damage to this row.
    """
    query = """
        insert into ai_decisions
          (business_id, conversation_id, customer_id, event_type, status,
           summary, detail, confidence, tool_name, duration_ms)
        values ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10)
        returning id
    """
    args = (
        business_id,
        conversation_id,
        customer_id,
        event_type,
        status,
        summary,
        json.dumps(detail or {}),
        confidence,
        tool_name,
        duration_ms,
    )

    try:
        if conn is not None:
            # Nested transaction == SAVEPOINT. If this insert fails, only the
            # savepoint rolls back and the caller's transaction stays usable.
            async with conn.transaction():
                return str(await conn.fetchval(query, *args))
        return str(await pool.fetchval(query, *args))
    except Exception:
        log.exception("failed to record ai_decision event_type=%s", event_type)
        return None
