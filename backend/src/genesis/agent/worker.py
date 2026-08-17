"""The voice agent worker.

Registers with LiveKit on startup and is dispatched into a room when a call
begins. Runs as its own process:

    make agent

Tools call the domain layer in-process. There is no HTTP hop between the model
deciding to book and the booking happening, which matters because every
millisecond of tool latency is audible as hesitation in a conversation.
"""

from __future__ import annotations

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
)
from livekit.plugins import openai as lk_openai

from genesis.agent import tools as T
from genesis.db import pool
from genesis.domain.observability import decisions
from genesis.domain.scheduling import booking
from genesis.settings import settings

log = logging.getLogger("genesis.agent")

PROMPT = (Path(__file__).resolve().parents[1] / "ai" / "prompts" / "system.md").read_text()

GREETING = (
    "Greet the caller: say this is Apex Climate Care and that you are the AI "
    "assistant, then ask how you can help. One sentence."
)


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
        self, _: RunContext, service: str, preferred_time: str = ""
    ) -> str:
        """Find real bookable times for a service and hold them briefly.

        Args:
            service: The service wanted, e.g. "AC service" or "gas refill".
            preferred_time: Optional — "morning", "afternoon" or "evening".
        """
        return await T.find_slots(self.state, service, preferred_time)

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
            ctx.create_task(
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
        await pool.execute(
            "update conversations set status = 'ended', ended_at = now() where id = $1",
            conversation_id,
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
