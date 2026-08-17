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
        # Wait for the goodbye to finish playing. Tearing the room down while
        # audio is still in flight cuts the agent off mid-word, which sounds
        # like a crash rather than a hang-up.
        await ctx.wait_for_playout()

        await decisions.record(
            business_id=settings.demo_business_id,
            conversation_id=self.state.conversation_id,
            customer_id=self.state.customer_id,
            event_type="call_ended_by_agent",
            summary="Agent ended the call",
            tool_name="end_call",
        )

        job = get_job_context()
        await job.delete_room()
        return "Call ended."


async def entrypoint(ctx: JobContext) -> None:
    await pool.init_pool()
    await ctx.connect()

    conversation_id = await pool.fetchval(
        """
        insert into conversations (business_id, channel, status, livekit_room)
        values ($1, 'voice', 'active', $2)
        returning id
        """,
        settings.demo_business_id,
        ctx.room.name,
    )
    state = T.SessionState(conversation_id=str(conversation_id))

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

    await session.start(agent=Receptionist(state), room=ctx.room)
    await session.generate_reply(instructions=GREETING)


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
