"""The voice agent worker.

Registers with LiveKit on startup and is dispatched into a room when a call
begins. Runs as its own process:

    make agent

Tools call the domain layer in-process. There is no HTTP hop between the model
deciding to book and the booking happening, which matters because every
millisecond of tool latency is audible as hesitation in a conversation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
    get_job_context,
)
from livekit.plugins import openai as lk_openai

from genesis.agent import tools as T
from genesis.db import pool
from genesis.domain.observability import decisions, usage
from genesis.domain.scheduling import booking
from genesis.settings import settings

log = logging.getLogger("genesis.agent")

PROMPT = (Path(__file__).resolve().parents[1] / "ai" / "prompts" / "system.md").read_text()

GREETING = (
    "Greet the caller: say this is Apex Climate Care and that you are the AI "
    "assistant, then ask how you can help. One sentence."
)

# --------------------------------------------------------------------------
# Outbound calls — review requests, payment reminders, reactivation
#
# There is no telephony here and nothing goes out over Telegram: the "call" is
# this same voice agent, joined from the dashboard the moment the owner clicks
# a button on a job, invoice, or lead. The room already carries its purpose
# and facts as metadata, set by /api/calls/join before anyone connects — but
# unlike a real phone line there is no caller ID on this end, so the agent
# still opens by confirming who picked up before saying anything else.
# --------------------------------------------------------------------------

_OUTBOUND_BRIEF: dict[str, str] = {
    "review": (
        "You are calling {customer_name} on behalf of Apex Climate Care about "
        "the {service} completed on {job_date}. Greet them by first name, say "
        "why you're calling, ask how the service went, and ask if they would "
        "give a quick rating from 1 to 5. Thank them for whatever they say. "
        "Keep it short and warm — this is one question, not an interrogation."
    ),
    "payment": (
        "You are calling {customer_name} on behalf of Apex Climate Care about "
        "invoice {invoice_number} for Rs {amount}. Greet them by first name, "
        "explain you're calling about the outstanding invoice, and politely "
        "ask when they can settle it. Do not be aggressive even if it is "
        "overdue — this is a reminder, not a demand. If they say they already "
        "paid, thank them and say the team will check."
    ),
    "reactivation": (
        "You are calling {customer_name} on behalf of Apex Climate Care. It "
        "has been a while since their last service. Greet them by first name, "
        "mention it has been some time, and ask if they would like to book a "
        "service. If they are interested, tell them someone will follow up to "
        "find a slot — you cannot book directly on this call. Keep it brief "
        "and not pushy; if they are not interested, thank them and end warmly."
    ),
}

OUTBOUND_GREETING = (
    "Open the call now, following your instructions — start with the identity check."
)


def _outbound_instructions(context: dict) -> str:
    name = context.get("customer_name", "the customer")
    brief = _OUTBOUND_BRIEF[context["purpose"]].format(
        customer_name=name,
        service=context.get("service", "the recent job"),
        job_date=context.get("job_date", "recently"),
        invoice_number=context.get("invoice_number", ""),
        amount=context.get("amount", ""),
    )
    identity_check = (
        f'Start the call by asking "Is this {name}?" — nothing else first, no '
        f"greeting before it. Wait for them to confirm. If they say yes (or "
        f"anything that is not a clear no), continue into the reason for your "
        f"call below. If they say no or seem to be the wrong person, apologise "
        f"for the mix-up and end the call without saying why you called."
    )
    return (
        f"{identity_check}\n\n{brief}\n\nSpeak naturally, one or two sentences "
        "per turn. Never invent facts beyond what you were just told."
    )


async def _summarise(conversation_id: str) -> str | None:
    """One line describing what the call was about, for the Conversations list.

    Best-effort: a call that cannot be summarised is still a call worth having
    a transcript of, so failure returns None and leaves the column untouched.
    """
    rows = await pool.fetch(
        """select role, content from messages
            where conversation_id = $1 order by created_at limit 40""",
        conversation_id,
    )
    if not rows:
        return None

    transcript = "\n".join(
        f"{'Customer' if r['role'] == 'customer' else 'AI'}: {r['content']}" for r in rows
    )

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=10.0)
        response = await client.chat.completions.create(
            model=settings.reasoning_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Summarise this phone call in one short sentence, from the "
                        "business's point of view. State what the customer wanted and "
                        "what happened. No preamble."
                    ),
                },
                {"role": "user", "content": transcript[:4000]},
            ],
            max_tokens=60,
            temperature=0.2,
        )
        await usage.record_completion(
            response, purpose="summary", conversation_id=conversation_id
        )
        return (response.choices[0].message.content or "").strip() or None
    except Exception:
        log.warning("could not summarise conversation %s", conversation_id, exc_info=True)
        return None


class Receptionist(Agent):
    def __init__(self, state: T.SessionState) -> None:
        super().__init__(instructions=PROMPT)
        self.state = state

    # ---------------------------------------------------------- identity

    @function_tool
    async def identify_customer(
        self, _: RunContext, name: str, phone: str = ""
    ) -> str:
        """Look up the caller by name, creating them if they are new.

        Args:
            name: The caller's full name as they said it.
            phone: Their phone number, if they gave one.
        """
        return await T.identify_customer(self.state, name, phone)

    # ---------------------------------------------------------- services

    @function_tool
    async def list_services(self, _: RunContext) -> str:
        """List the services offered, with durations and prices."""
        return await T.list_services(self.state)

    # ------------------------------------------------------------- slots

    @function_tool
    async def find_available_times(
        self,
        _: RunContext,
        service: str,
        preferred_time: str = "",
        location: str = "",
    ) -> str:
        """Find real bookable times for a service and hold them briefly.

        Args:
            service: The service wanted, e.g. "AC service" or "gas refill".
            preferred_time: Optional — "morning", "afternoon" or "evening".
            location: The customer's area, e.g. "Indiranagar". Ask if unknown.
        """
        return await T.find_slots(self.state, service, preferred_time, location)

    @function_tool
    async def book_the_appointment(self, _: RunContext, option: int) -> str:
        """Book one of the times you just offered.

        Args:
            option: Which option the customer chose, starting at 1.
        """
        return await T.confirm_booking(self.state, option)

    # ------------------------------------------------------ existing job

    @function_tool
    async def find_existing_appointment(self, _: RunContext) -> str:
        """Find the caller's next upcoming booking."""
        return await T.find_my_appointment(self.state)

    @function_tool
    async def cancel_appointment(self, _: RunContext) -> str:
        """Cancel the booking you just found. Confirm with the caller first."""
        return await T.cancel_my_appointment(self.state)

    @function_tool
    async def reschedule_appointment(self, _: RunContext, option: int) -> str:
        """Move the found booking to one of the times you just offered.

        Args:
            option: Which new option the customer chose, starting at 1.
        """
        return await T.move_appointment(self.state, option)

    # ------------------------------------------------------------ hang up

    @function_tool
    async def end_call(self, ctx: RunContext) -> str:
        """Hang up. Say goodbye to the caller BEFORE calling this.

        Use when the caller says goodbye, says they are done, or the
        conversation has clearly finished.
        """
        return await _end_call(ctx, self.state)


async def _end_call(ctx: RunContext, state: T.SessionState) -> str:
    # Wait for the goodbye to finish playing. Tearing the room down while
    # audio is still in flight cuts the agent off mid-word, which sounds
    # like a crash rather than a hang-up.
    await ctx.wait_for_playout()

    await decisions.record(
        business_id=settings.demo_business_id,
        conversation_id=state.conversation_id,
        customer_id=state.customer_id,
        event_type="call_ended_by_agent",
        summary="Agent ended the call",
        tool_name="end_call",
    )

    job = get_job_context()
    await job.delete_room()
    return "Call ended."


class OutboundAgent(Agent):
    """A single-purpose call — review request, payment reminder, or
    reactivation. No booking tools: the job is one short conversation, not
    the full receptionist flow."""

    def __init__(self, state: T.SessionState, instructions: str) -> None:
        super().__init__(instructions=instructions)
        self.state = state

    @function_tool
    async def end_call(self, ctx: RunContext) -> str:
        """Hang up. Say goodbye to the caller BEFORE calling this.

        Use when the caller says goodbye, says they are done, or the
        conversation has clearly finished.
        """
        return await _end_call(ctx, self.state)


async def entrypoint(ctx: JobContext) -> None:
    await pool.init_pool()
    await ctx.connect()

    # Outbound calls (review, payment reminder, reactivation) carry their
    # purpose and facts in room metadata, set by /api/calls/join before the
    # customer's browser ever connects. Its absence means an ordinary inbound
    # call, which is the overwhelming majority of rooms this worker ever sees.
    outbound: dict | None = None
    if ctx.room.metadata:
        try:
            outbound = json.loads(ctx.room.metadata)
        except (json.JSONDecodeError, TypeError):
            log.warning("unreadable room metadata; treating as inbound", exc_info=True)

    conversation_id = await pool.fetchval(
        """
        insert into conversations (business_id, customer_id, channel, status, livekit_room)
        values ($1, $2, 'voice', 'active', $3)
        returning id
        """,
        settings.demo_business_id,
        outbound["customer_id"] if outbound else None,
        ctx.room.name,
    )
    state = T.SessionState(conversation_id=str(conversation_id))
    if outbound:
        state.customer_id = outbound.get("customer_id")
        state.customer_name = outbound.get("customer_name")

    # Fire-and-forget writes from synchronous event handlers. asyncio holds
    # only a weak reference to a running task, so without this set a
    # transcript or metrics write can be collected before it completes.
    background: set[asyncio.Task] = set()

    def spawn(coro) -> None:
        task = asyncio.create_task(coro)
        background.add(task)
        task.add_done_callback(background.discard)

    await decisions.record(
        business_id=settings.demo_business_id,
        conversation_id=str(conversation_id),
        event_type="call_started",
        summary="Incoming customer call",
        detail={"room": ctx.room.name},
    )

    session = AgentSession(
        llm=lk_openai.realtime.RealtimeModel(
            model="gpt-realtime",
            voice="marin",
            api_key=settings.openai_api_key,
        )
    )

    # Token and minute accounting. Realtime audio is the expensive part of this
    # system by an order of magnitude, so it is measured rather than estimated.
    @session.on("metrics_collected")
    def _on_metrics(event) -> None:
        m = getattr(event, "metrics", None)
        if getattr(m, "type", None) != "realtime_model_metrics":
            return

        inp = getattr(m, "input_token_details", None)
        out = getattr(m, "output_token_details", None)
        spawn(
            usage.record(
                source="realtime",
                model="gpt-realtime",
                purpose="voice",
                conversation_id=str(conversation_id),
                input_text_tokens=getattr(inp, "text_tokens", 0) or 0,
                input_audio_tokens=getattr(inp, "audio_tokens", 0) or 0,
                input_cached_tokens=getattr(inp, "cached_tokens", 0) or 0,
                output_text_tokens=getattr(out, "text_tokens", 0) or 0,
                output_audio_tokens=getattr(out, "audio_tokens", 0) or 0,
                duration_seconds=float(getattr(m, "duration", 0.0) or 0.0),
            )
        )

    # Persist both sides of the conversation as it happens, rather than trying
    # to reconstruct it at the end. A call that drops mid-sentence still leaves
    # a readable transcript behind.
    @session.on("conversation_item_added")
    def _on_item(event) -> None:
        item = getattr(event, "item", None)
        role = getattr(item, "role", None)
        if role not in ("user", "assistant"):
            return

        content = getattr(item, "content", None) or []
        text = " ".join(c for c in content if isinstance(c, str)).strip()
        if not text:
            return

        spawn(
            pool.execute(
                """
                insert into messages (business_id, conversation_id, role, content)
                values ($1, $2, $3, $4)
                """,
                settings.demo_business_id,
                conversation_id,
                "customer" if role == "user" else "agent",
                text,
            )
        )

    # The safety tripwire runs on every transcribed user turn, before the model
    # gets a chance to decide anything. A tripwire the model can choose not to
    # pull is not a tripwire.
    @session.on("user_input_transcribed")
    def _on_transcript(event) -> None:
        text = getattr(event, "transcript", "") or ""
        if not getattr(event, "is_final", True) or state.safety_triggered:
            return
        if T.check_safety(text):
            state.safety_triggered = True
            log.warning("safety tripwire fired")
            session.interrupt()
            session.say(T.SAFETY_RESPONSE, allow_interruptions=False)
            spawn(
                decisions.record(
                    business_id=settings.demo_business_id,
                    conversation_id=str(conversation_id),
                    customer_id=state.customer_id,
                    event_type="safety_tripwire",
                    status="blocked",
                    summary="Possible emergency mentioned — caller directed to emergency services",
                    detail={"matched": text[:160]},
                )
            )

    async def _cleanup() -> None:
        # Holds left behind would sterilise the calendar until they expire.
        released = await booking.release(str(conversation_id))
        summary = await _summarise(str(conversation_id))
        await pool.execute(
            """
            update conversations
               set status = 'ended', ended_at = now(), summary = coalesce($2, summary)
             where id = $1
            """,
            conversation_id,
            summary,
        )
        await decisions.record(
            business_id=settings.demo_business_id,
            conversation_id=str(conversation_id),
            customer_id=state.customer_id,
            event_type="call_ended",
            summary="Call ended",
            detail={"holds_released": released},
        )

    ctx.add_shutdown_callback(_cleanup)

    if outbound:
        agent = OutboundAgent(state, _outbound_instructions(outbound))
        greeting = OUTBOUND_GREETING
    else:
        agent = Receptionist(state)
        greeting = GREETING

    await session.start(agent=agent, room=ctx.room)
    await session.generate_reply(instructions=greeting)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Credentials are passed explicitly rather than left to the LiveKit CLI's
    # own environment lookup: the rest of the system reads them from the
    # repository .env via pydantic-settings, and having two sources of truth
    # for the same three values is how a demo ends up connecting to nothing.
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            ws_url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
    )
