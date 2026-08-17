"""The automation worker.

Claims due jobs, runs them, records the outcome. Runs as its own process:

    make automation

Jobs are claimed with SELECT ... FOR UPDATE SKIP LOCKED, which is what lets
several workers share one queue without ever handing the same job to two of
them. There is no in-memory queue and no scheduler state — the database is the
queue, so a worker can be killed mid-run and nothing is lost.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from datetime import UTC, datetime

from genesis.automation.jobs.handlers import HANDLERS
from genesis.db import pool
from genesis.settings import settings

log = logging.getLogger("genesis.automation")

POLL_INTERVAL_SECONDS = 10
BATCH_SIZE = 5

_shutdown = asyncio.Event()


async def claim_batch(limit: int = BATCH_SIZE) -> list[dict]:
    """Atomically take ownership of up to `limit` due jobs."""
    async with pool.transaction() as conn:
        rows = await conn.fetch(
            """
            with due as (
              select id from automation_jobs
               where status = 'pending' and scheduled_for <= now()
               order by scheduled_for
               for update skip locked
               limit $1
            )
            update automation_jobs j
               set status = 'claimed', claimed_at = now(), attempts = j.attempts + 1
              from due
             where j.id = due.id
            returning j.id, j.job_type, j.payload, j.attempts, j.max_attempts
            """,
            limit,
        )
        return [dict(r) for r in rows]


async def run_job(job: dict) -> None:
    job_id = job["id"]
    job_type = job["job_type"]
    handler = HANDLERS.get(job_type)

    if handler is None:
        await _fail(job_id, f"No handler for job type '{job_type}'", terminal=True)
        return

    payload = job["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)

    try:
        result = await handler(payload)
    except Exception as exc:  # noqa: BLE001 — the worker must never die on one job
        log.exception("job %s (%s) failed", job_id, job_type)
        terminal = job["attempts"] >= job["max_attempts"]
        await _fail(job_id, str(exc)[:400], terminal=terminal)
        return

    # A Guard block is a correct outcome, not a failure. The job did its work;
    # the system decided not to send. Retrying would just be blocked again.
    outcome = "sent" if result.sent else f"blocked ({result.reason})"
    await pool.execute(
        """
        update automation_jobs
           set status = 'succeeded', completed_at = now(), last_error = $2
         where id = $1
        """,
        job_id,
        None if result.sent else result.reason,
    )
    log.info("%s %s — %s", job_type, job_id, outcome)


async def _fail(job_id, error: str, *, terminal: bool) -> None:
    await pool.execute(
        """
        update automation_jobs
           set status = $2,
               last_error = $3,
               completed_at = case when $2 = 'failed' then now() end,
               -- put it back in the queue with a delay if retries remain
               scheduled_for = case when $2 = 'pending'
                                    then now() + interval '2 minutes'
                                    else scheduled_for end
         where id = $1
        """,
        job_id,
        "failed" if terminal else "pending",
        error,
    )


async def drain_once() -> int:
    """Run every currently-due job. Returns how many ran."""
    total = 0
    while not _shutdown.is_set():
        batch = await claim_batch()
        if not batch:
            break
        for job in batch:
            await run_job(job)
        total += len(batch)
    return total


async def sweep_expired_holds() -> int:
    """Expired slot holds must be reaped or availability silently shrinks."""
    result = await pool.execute(
        "delete from slot_holds where consumed_at is null and expires_at < now()"
    )
    return int(result.split()[-1]) if result.startswith("DELETE") else 0


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    await pool.init_pool()
    health = await pool.healthcheck()
    log.info("worker started — postgres %s", health["postgres"])
    if not settings.telegram_enabled:
        log.warning(
            "TELEGRAM_BOT_TOKEN not set — jobs will run and the Guard will "
            "block every send. That is correct behaviour, not a failure."
        )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown.set)

    while not _shutdown.is_set():
        try:
            ran = await drain_once()
            swept = await sweep_expired_holds()
            if ran or swept:
                log.info("cycle: %d job(s), %d expired hold(s) swept", ran, swept)
        except Exception:
            log.exception("worker cycle failed; continuing")

        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=POLL_INTERVAL_SECONDS)
        except TimeoutError:
            pass

    log.info("worker stopped at %s", datetime.now(UTC).isoformat(timespec="seconds"))
    await pool.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
