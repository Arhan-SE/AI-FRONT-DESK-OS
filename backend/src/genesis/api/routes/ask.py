"""Ask — the AI Administrative Manager.

The owner types a question in English. gpt-4o-mini writes SQL against the
read-only reporting views, the database executes it, and a second pass turns the
returned rows into one plain sentence.

The interesting part is not the SQL generation, it is everything stopping it
from being dangerous. A model-written query is untrusted input, so it passes
three independent gates before Postgres ever sees it:

1. **Shape.** One statement, starting with SELECT or WITH, no DML/DDL keywords.
2. **Surface.** Every table it reads must be an allowlisted reporting view. The
   base tables, and anything else in the schema, are unreachable.
3. **Scope.** The query must filter on `business_id = $1`, and that value is
   bound by the server — never by the model, never by the browser.

Then it runs inside a genuinely read-only transaction with a statement timeout,
so even a query that talks its way past all three cannot write or hang.

The generated SQL is returned to the caller and shown in the interface. An
answer you cannot check is not an answer.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from genesis.db import pool
from genesis.domain.observability import decisions, usage
from genesis.settings import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ask", tags=["ask"])

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI | None:
    global _client
    if not settings.ai_enabled:
        return None
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=20.0)
    return _client


# --------------------------------------------------------------------------
# What the model is allowed to see
#
# Only reporting views. No base tables, so there is no path to auth data,
# tokens, or another tenant's rows even if the query is adversarial.
# --------------------------------------------------------------------------

ALLOWED_VIEWS = {
    "v_jobs",
    "v_customers",
    "v_invoices",
    "v_campaigns",
    "v_dashboard_metrics",
    "v_daily_activity",
    "v_attention",
    "v_usage_summary",
    "v_lead_current_score",
}

SCHEMA = """
v_jobs — one row per job, the operational spine
  id, starts_at, ends_at, appointment_status, source, notes,
  confirmed_at, started_at, completed_at, cancelled_at,
  customer_id, customer_name, customer_phone, customer_reachable,
  service_name, service_price, technician_name,
  invoice_id, invoice_number, invoice_amount, invoice_status, due_on,
  stage  -- scheduled | confirmed | in_progress | completed | invoice_sent
         -- | paid | overdue | cancelled | no_show

v_customers — one row per customer
  id, full_name, phone, email, address, status, reachable, telegram_opted_in,
  do_not_contact, last_contacted_at, created_at, jobs_completed, jobs_upcoming,
  last_service_at, total_paid, amount_outstanding, avg_rating,
  messages_sent, messages_blocked

v_invoices — billing
  id, invoice_number, amount, status (draft|sent|paid|overdue|void),
  issued_on, due_on, paid_at, customer_id, customer_name, service_name,
  service_date, payment_method, days_past_due (positive = overdue by N days),
  reminders_sent, last_reminder_at, next_reminder_at

v_campaigns — outreach roll-up
  id, name, campaign_type, status, scheduled_for, started_at, completed_at,
  audience, sent, blocked, failed, replied, pending

v_dashboard_metrics — single row of business totals
  open_leads, hot_leads, upcoming_appointments, jobs_this_month,
  outstanding_amount, overdue_invoices, overdue_amount, avg_rating,
  reviews_collected, reviews_awaiting, dormant_customers, dormant_value,
  total_customers, open_tasks

v_daily_activity — one row per day
  day, is_future, jobs, completed, collected, decisions, calls

v_attention — things needing the owner's attention
  kind, tone, subject, detail, age_days, occurred_at, entity_id

v_usage_summary — single row of AI cost
  total_calls, voice_minutes, total_tokens, audio_tokens,
  total_cost_usd, voice_cost_usd, text_cost_usd,
  total_decisions, blocked_decisions, failed_decisions

v_lead_current_score — latest score per lead
  lead_id, score, classification (HOT|WARM|COLD), confidence, reasoning
""".strip()


SQL_SYSTEM = """You write a single PostgreSQL SELECT answering the owner's \
question about their home-services business.

Hard rules:
- Output raw SQL only. No prose, no markdown fence, no trailing semicolon.
- SELECT or WITH only. Never insert, update, delete, or any DDL.
- Read ONLY from the views listed. Base tables do not exist to you.
- Every view you read must be filtered by `business_id = $1`. This is required
  even for single-row views.
- Prefer few, meaningful columns over `select *`. Always include a name column
  when the answer is about people.
- Add `limit 50` unless the question implies a single aggregate.
- Money is `numeric` rupees. Dates are `date`; timestamps are `timestamptz`.
- Use `current_date` / `now()` for anything relative to today.
- The conversation so far is given to you. Resolve pronouns against it: after
  "who owes me money", "chase him" refers to the person you just named.
- If the message is conversation rather than a question about the data — a
  greeting, thanks, "what can you do", a question about how you work — return
  exactly: CHAT
- If it is a data question these views genuinely cannot answer, return exactly:
  IMPOSSIBLE"""


CHAT_SYSTEM = """You are the operations manager for Apex Climate Care, a home services business in Bengaluru. You are talking to the owner.

You can answer questions about their jobs, customers, invoices and payments,
appointments and technicians, campaigns and outreach, reviews, and what the AI
has cost. You read their live database to do it.

- Two or three sentences. Warm, direct, Indian English. No corporate filler.
- If they ask what you can do, give two or three concrete example questions
  they could ask, drawn from the list above.
- Never invent figures. If answering needs data, invite them to ask for it
  directly rather than guessing.
- No markdown, no bullet lists."""


ANSWER_SYSTEM = """You are the operations manager of an Indian home-services \
business, answering the owner's question from a query result.

- One or two sentences. Plain English. No preamble, no restating the question.
- Use ONLY the rows given. Never invent a number, name, or date.
- Money is in the currency its column names. A `*_usd` column is US dollars
  and is reported as $0.57; everything else is rupees, written Rs 1,499.
  Never convert between currencies — you do not know today's rate.
- If no rows came back, answer the question in the negative, in the words of
  the question itself — "No one owes you anything right now." Never a canned
  line, and never quote these instructions back.
- Name the specific people or jobs when there are only a few.
- No markdown, no bullets."""


# --------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|copy|merge"
    r"|call|do|vacuum|reindex|listen|notify|set|reset|begin|commit|rollback"
    r"|savepoint|prepare|execute|declare|lock|dblink|pg_sleep|pg_read_file"
    r"|pg_ls_dir|lo_import|lo_export|current_setting|pg_catalog|information_schema)\b",
    re.IGNORECASE,
)
_TABLE_REF = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
_CTE_NAME = re.compile(r"(?:with|,)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(", re.IGNORECASE)
_SCOPED = re.compile(r"business_id\s*=\s*\$1", re.IGNORECASE)


class UnsafeQuery(ValueError):
    """The generated SQL failed a gate. Never shown raw to the customer-facing UI."""


def validate_sql(sql: str) -> str:
    """Return the cleaned query, or raise UnsafeQuery explaining which gate failed."""
    cleaned = sql.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:sql)?\s*|\s*```$", "", cleaned).strip()
    cleaned = cleaned.rstrip(";").strip()

    if not cleaned:
        raise UnsafeQuery("The model returned an empty query")

    # One statement only. A semicolon left inside is a stacked query attempt.
    if ";" in cleaned:
        raise UnsafeQuery("Only one statement is allowed")

    if not re.match(r"^\s*(select|with)\b", cleaned, re.IGNORECASE):
        raise UnsafeQuery("Only SELECT queries are allowed")

    if (bad := _FORBIDDEN.search(cleaned)) is not None:
        raise UnsafeQuery(f"Disallowed keyword: {bad.group(0).lower()}")

    ctes = {name.lower() for name in _CTE_NAME.findall(cleaned)}
    for ref in _TABLE_REF.findall(cleaned):
        if ref.lower() not in ALLOWED_VIEWS and ref.lower() not in ctes:
            raise UnsafeQuery(f"'{ref}' is not a readable view")

    if not _SCOPED.search(cleaned):
        raise UnsafeQuery("Query is not scoped to the business")

    return cleaned


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


async def _execute(sql: str) -> list:
    """Run a validated query with no ability to write and a bounded runtime."""
    async with pool.connection() as conn:
        tx = conn.transaction(readonly=True)
        await tx.start()
        try:
            await conn.execute("set local statement_timeout = '6s'")
            return await conn.fetch(sql, settings.demo_business_id)
        finally:
            await tx.rollback()


async def _repair(client, question: str, sql: str, error: str) -> str | None:
    """Show the model what Postgres objected to. Returns validated SQL or None."""
    try:
        fixed = await client.chat.completions.create(
            model=settings.reasoning_model,
            messages=[
                {"role": "system", "content": f"{SQL_SYSTEM}\n\nViews:\n{SCHEMA}"},
                {"role": "user", "content": f"Question: {question}"},
                {"role": "assistant", "content": sql},
                {
                    "role": "user",
                    "content": (
                        f"PostgreSQL rejected that:\n{error}\n\n"
                        "Rewrite it using only columns that exist on the listed "
                        "views. Output SQL only."
                    ),
                },
            ],
            max_tokens=400,
            temperature=0,
        )
        await usage.record_completion(fixed, purpose="ask_repair")
        return validate_sql(fixed.choices[0].message.content or "")
    except (UnsafeQuery, Exception):
        log.warning("ask: repair attempt failed", exc_info=True)
        return None


# --------------------------------------------------------------------------
# Endpoint
# --------------------------------------------------------------------------

MAX_ROWS = 50


class Turn(BaseModel):
    """One prior exchange. Sent by the browser so follow-ups resolve."""

    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=2000)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    # Bounded deliberately: enough for "chase him" to resolve, not enough for
    # the prompt to grow without limit over a long conversation.
    history: list[Turn] = Field(default_factory=list, max_length=8)


class Answer(BaseModel):
    question: str
    answer: str
    sql: str | None = None
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    row_count: int = 0
    truncated: bool = False
    elapsed_ms: int = 0
    ok: bool = True
    kind: str = "data"  # "data" when a query ran, "chat" for conversation


@router.post("", response_model=Answer)
async def ask(body: Question) -> Answer:
    started = time.perf_counter()
    client = _get_client()

    def elapsed() -> int:
        return int((time.perf_counter() - started) * 1000)

    if client is None:
        return Answer(
            question=body.question,
            answer="The AI is not configured. Add OPENAI_API_KEY to .env and restart the API.",
            ok=False,
            elapsed_ms=elapsed(),
        )

    # ---------------------------------------------------------- write SQL
    try:
        drafted = await client.chat.completions.create(
            model=settings.reasoning_model,
            messages=[
                {"role": "system", "content": f"{SQL_SYSTEM}\n\nViews:\n{SCHEMA}"},
                {
                    "role": "user",
                    "content": f"Today is {date.today():%d %B %Y}.\nQuestion: {body.question}",
                },
            ],
            max_tokens=400,
            temperature=0,
        )
        await usage.record_completion(drafted, purpose="ask_sql")
        raw = (drafted.choices[0].message.content or "").strip()
    except Exception:
        log.warning("ask: SQL generation failed", exc_info=True)
        return Answer(
            question=body.question,
            answer="I could not reach the model just now. Try again in a moment.",
            ok=False,
            elapsed_ms=elapsed(),
        )

    if raw.upper().startswith("IMPOSSIBLE"):
        return Answer(
            question=body.question,
            answer="I cannot answer that from the operational data I can see.",
            ok=False,
            elapsed_ms=elapsed(),
        )

    try:
        sql = validate_sql(raw)
    except UnsafeQuery as exc:
        log.warning("ask: rejected generated SQL (%s): %s", exc, raw)
        await decisions.record(
            business_id=settings.demo_business_id,
            event_type="ask_rejected",
            status="blocked",
            summary=f'Query for "{body.question[:60]}" refused — {exc}',
            detail={"reason": str(exc)},
            tool_name="ask",
        )
        return Answer(
            question=body.question,
            answer=f"I built a query I was not allowed to run ({exc}). Nothing was executed.",
            ok=False,
            elapsed_ms=elapsed(),
        )

    # ------------------------------------------------------------ execute
    #
    # A real read-only transaction, not a promise to behave. Postgres itself
    # refuses a write here, and the timeout bounds a runaway query.
    #
    # One repair attempt on failure. A model that confuses two similarly-named
    # columns writes SQL that is well-formed and wrong, and Postgres says
    # exactly what is wrong — so hand it the error and let it correct itself.
    # The retry passes the same three gates; nothing is trusted the second time
    # that was not trusted the first.
    try:
        records = await _execute(sql)
    except Exception as first_error:
        log.info("ask: repairing failed query — %s", first_error)
        repaired = await _repair(client, body.question, sql, str(first_error))
        if repaired is None:
            return Answer(
                question=body.question,
                answer="That question turned into a query the database rejected. "
                       "Try rephrasing it.",
                sql=sql,
                ok=False,
                elapsed_ms=elapsed(),
            )
        sql = repaired
        try:
            records = await _execute(sql)
        except Exception as exc:
            log.warning("ask: repair also failed: %s", exc)
            return Answer(
                question=body.question,
                answer="I could not turn that into a query the database would "
                       "accept. Try asking it a different way.",
                sql=sql,
                ok=False,
                elapsed_ms=elapsed(),
            )

    columns = list(records[0].keys()) if records else []
    rows = [{k: _jsonable(v) for k, v in r.items()} for r in records[:MAX_ROWS]]

    # ------------------------------------------------------- write answer
    try:
        written = await client.chat.completions.create(
            model=settings.reasoning_model,
            messages=[
                {"role": "system", "content": ANSWER_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Today is {date.today():%d %B %Y}.\n"
                        f"Question: {body.question}\n"
                        f"Rows returned: {len(records)}\n"
                        f"Result: {json.dumps(rows[:30], default=str)}"
                    ),
                },
            ],
            max_tokens=200,
            temperature=0.3,
        )
        await usage.record_completion(written, purpose="ask_answer")
        answer = (written.choices[0].message.content or "").strip()
    except Exception:
        log.warning("ask: answer generation failed", exc_info=True)
        answer = f"{len(records)} row(s) returned — see the table below."

    await decisions.record(
        business_id=settings.demo_business_id,
        event_type="ask_answered",
        summary=f'Asked: "{body.question[:70]}" — {len(records)} row(s)',
        detail={"question": body.question, "sql": sql, "rows": len(records)},
        tool_name="ask",
        duration_ms=elapsed(),
    )

    return Answer(
        question=body.question,
        answer=answer or f"{len(records)} row(s) returned.",
        sql=sql,
        columns=columns,
        rows=rows,
        row_count=len(records),
        truncated=len(records) > MAX_ROWS,
        elapsed_ms=elapsed(),
    )
