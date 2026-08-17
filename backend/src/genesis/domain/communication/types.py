"""Message taxonomy.

The transactional/marketing split is the single most consequential thing in this
module. Transactional messages are things the customer's own action earned them
— a confirmation for an appointment they booked, a reminder for a job they
scheduled. Marketing messages are things the business wants. They get
frequency caps, cooldowns and quiet hours; transactional messages do not,
because silently suppressing a booking confirmation is worse than sending it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Category(StrEnum):
    TRANSACTIONAL = "transactional"
    MARKETING = "marketing"


class MessageType(StrEnum):
    APPOINTMENT_CONFIRMATION = "appointment_confirmation"
    APPOINTMENT_REMINDER = "appointment_reminder"
    POST_SERVICE_FOLLOWUP = "post_service_followup"
    INVOICE_SENT = "invoice_sent"
    PAYMENT_REMINDER = "payment_reminder"
    REVIEW_REQUEST = "review_request"
    REACTIVATION = "reactivation"
    SEASONAL = "seasonal"


CATEGORY_OF: dict[MessageType, Category] = {
    MessageType.APPOINTMENT_CONFIRMATION: Category.TRANSACTIONAL,
    MessageType.APPOINTMENT_REMINDER: Category.TRANSACTIONAL,
    MessageType.POST_SERVICE_FOLLOWUP: Category.TRANSACTIONAL,
    MessageType.INVOICE_SENT: Category.TRANSACTIONAL,
    MessageType.PAYMENT_REMINDER: Category.TRANSACTIONAL,
    MessageType.REVIEW_REQUEST: Category.TRANSACTIONAL,
    MessageType.REACTIVATION: Category.MARKETING,
    MessageType.SEASONAL: Category.MARKETING,
}


class BlockCode(StrEnum):
    """Why the Guard refused. Stored so the UI can explain a non-send."""

    NO_CHANNEL_CONFIGURED = "no_channel_configured"
    CUSTOMER_NOT_FOUND = "customer_not_found"
    NO_TELEGRAM_CHAT = "no_telegram_chat"
    NOT_OPTED_IN = "not_opted_in"
    DO_NOT_CONTACT = "do_not_contact"
    DUPLICATE = "duplicate"
    COOLDOWN = "cooldown"
    MONTHLY_CAP = "monthly_cap"
    QUIET_HOURS = "quiet_hours"


@dataclass(frozen=True, slots=True)
class GuardVerdict:
    allowed: bool
    code: BlockCode | None = None
    reason: str | None = None

    @staticmethod
    def allow() -> GuardVerdict:
        return GuardVerdict(True)

    @staticmethod
    def block(code: BlockCode, reason: str) -> GuardVerdict:
        return GuardVerdict(False, code, reason)


@dataclass(frozen=True, slots=True)
class SendResult:
    sent: bool
    blocked: bool
    code: BlockCode | None
    reason: str | None
    message_log_id: str | None = None
    telegram_message_id: int | None = None
