from enum import StrEnum


class TelegramEventType(StrEnum):
    PROPOSAL_CREATED = "proposal_created"
    USER_REGISTERED = "user_registered"


class TelegramEventStatus(StrEnum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    FAILED = "failed"
