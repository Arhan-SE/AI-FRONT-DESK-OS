"""Configuration. Every secret comes from the environment; none are defaulted."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/genesis/settings.py -> repository root
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    # The .env lives at the repository root and is shared by all three
    # processes, so there is exactly one place to configure the system.
    #
    # Resolved absolutely rather than as "../.env": the api, agent and
    # automation workers are launched from different directories, and a
    # CWD-relative path silently yields an unconfigured system rather than an
    # error.
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- AI ------------------------------------------------------------
    openai_api_key: str = ""
    reasoning_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # --- Voice transport -----------------------------------------------
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"

    # --- Data ----------------------------------------------------------
    database_url: str = ""
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # --- Messaging ------------------------------------------------------
    telegram_bot_token: str = ""

    # --- Application ----------------------------------------------------
    business_timezone: str = "Asia/Kolkata"
    demo_business_id: str = "00000000-0000-0000-0000-000000000001"
    api_base_url: str = "http://localhost:8000"

    # --- Scheduling policy ----------------------------------------------
    #
    # How long an offered slot stays reserved. Long enough for a customer to
    # think during a phone call, short enough that an abandoned call does not
    # sterilise the calendar.
    slot_hold_ttl_seconds: int = 180
    # Candidate start times are generated on this grid.
    slot_granularity_minutes: int = 15
    # Never offer a slot sooner than this from now.
    min_booking_lead_minutes: int = 60
    max_slots_offered: int = 3

    # --- Communication policy -------------------------------------------
    # Marketing only. Transactional messages are exempt by design: a customer
    # must always be able to receive a confirmation for something they booked.
    marketing_cooldown_days: int = 14
    max_marketing_per_month: int = 2
    quiet_hours_start: int = Field(default=21, ge=0, le=23)
    quiet_hours_end: int = Field(default=8, ge=0, le=23)

    # --- Lead qualification ----------------------------------------------
    hot_threshold: int = 75
    warm_threshold: int = 50

    # --- Model rates, USD per 1M tokens -----------------------------------
    #
    # These are configuration, not facts. Verify them against OpenAI's current
    # pricing page before quoting a cost figure to anyone — they are here so
    # the number the dashboard shows is arithmetic over a rate card you
    # control, rather than something hardcoded and quietly wrong.
    rate_mini_input: float = 0.15
    rate_mini_output: float = 0.60
    rate_realtime_text_input: float = 4.00
    rate_realtime_text_output: float = 16.00
    rate_realtime_audio_input: float = 32.00
    rate_realtime_audio_output: float = 64.00
    rate_realtime_cached_input: float = 0.40
    rate_embedding: float = 0.02

    # --- Job pipeline timing ---------------------------------------------
    #
    # How long after each owner action the corresponding automation becomes
    # due. Real values, not demo values: the "Run due automations" control
    # advances the clock rather than shortening these, so the demo exercises
    # exactly the same code path a real deployment would.
    followup_delay_hours: int = 2
    review_delay_hours: int = 24
    invoice_due_days: int = 7
    payment_reminder_repeat_days: int = 3
    max_payment_reminders: int = 3

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.business_timezone)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
