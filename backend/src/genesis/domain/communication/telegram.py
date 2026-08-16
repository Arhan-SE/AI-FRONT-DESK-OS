"""Telegram transport.

Outbound only, over the official Bot API. Inbound updates are handled by the
automation worker's long poller — the backend always dials out, which is what
lets the whole system run on localhost with no tunnel and no public URL.

Telegram's documented limits are roughly 30 messages/second overall and 1
message/second to a single chat. Exceeding them earns a 429 with a retry_after,
so both limits are enforced locally rather than discovered the hard way.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from telegram import Bot
from telegram.error import Forbidden, RetryAfter, TelegramError

from genesis.settings import settings

log = logging.getLogger(__name__)

_GLOBAL_PER_SECOND = 25.0  # headroom under the documented 30
_PER_CHAT_INTERVAL = 1.05  # headroom over the documented 1/sec


@dataclass(slots=True)
class DeliveryResult:
    ok: bool
    message_id: int | None = None
    error: str | None = None
    # Telegram told us this user has blocked the bot. The caller should mark
    # them unreachable rather than retrying forever.
    unreachable: bool = False


class _RateLimiter:
    """Global token bucket plus a per-chat spacing gate."""

    def __init__(self) -> None:
        self._tokens = _GLOBAL_PER_SECOND
        self._last_refill = time.monotonic()
        self._last_sent: dict[int, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, chat_id: int) -> None:
        async with self._lock:
            now = time.monotonic()

            self._tokens = min(
                _GLOBAL_PER_SECOND,
                self._tokens + (now - self._last_refill) * _GLOBAL_PER_SECOND,
            )
            self._last_refill = now

            if self._tokens < 1:
                wait = (1 - self._tokens) / _GLOBAL_PER_SECOND
                await asyncio.sleep(wait)
                self._tokens = 0
            else:
                self._tokens -= 1

            last = self._last_sent.get(chat_id)
            if last is not None:
                gap = time.monotonic() - last
                if gap < _PER_CHAT_INTERVAL:
                    await asyncio.sleep(_PER_CHAT_INTERVAL - gap)

            self._last_sent[chat_id] = time.monotonic()


_limiter = _RateLimiter()
_bot: Bot | None = None


def get_bot() -> Bot | None:
    global _bot
    if not settings.telegram_enabled:
        return None
    if _bot is None:
        _bot = Bot(token=settings.telegram_bot_token)
    return _bot


async def send_message(chat_id: int, text: str, *, attempts: int = 3) -> DeliveryResult:
    bot = get_bot()
    if bot is None:
        return DeliveryResult(ok=False, error="No Telegram bot token configured")

    for attempt in range(1, attempts + 1):
        await _limiter.acquire(chat_id)
        try:
            msg = await bot.send_message(chat_id=chat_id, text=text)
            return DeliveryResult(ok=True, message_id=msg.message_id)

        except RetryAfter as exc:
            # Telegram is explicit about how long to wait. Honour it.
            wait = float(getattr(exc, "retry_after", 1.0))
            log.warning("telegram 429, waiting %.1fs (attempt %d)", wait, attempt)
            await asyncio.sleep(wait + 0.25)

        except Forbidden:
            # The user blocked the bot or deleted the chat. Retrying cannot fix
            # this, so report it as terminal.
            return DeliveryResult(
                ok=False, error="Customer has blocked the bot", unreachable=True
            )

        except TelegramError as exc:
            log.warning("telegram error (attempt %d): %s", attempt, exc)
            if attempt == attempts:
                return DeliveryResult(ok=False, error=str(exc)[:300])
            await asyncio.sleep(0.5 * attempt)

    return DeliveryResult(ok=False, error="Exhausted retries")
