from enum import StrEnum


class TelegramEventType(StrEnum):
    EMAIL_VERIFIED = "email_verified"
    EMAIL_VERIFICATION_RESENT = "email_verification_resent"
    MATERIAL_APPROVED = "material_approved"
    MATERIAL_REJECTED = "material_rejected"
    MATERIAL_REVISION_REQUESTED = "material_revision_requested"
    MATERIAL_SUBMITTED_FOR_REVIEW = "material_submitted_for_review"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PROPOSAL_CREATED = "proposal_created"
    PROPOSAL_APPROVED = "proposal_approved"
    PROPOSAL_REJECTED = "proposal_rejected"
    USER_REGISTERED = "user_registered"


class TelegramEventStatus(StrEnum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    FAILED = "failed"
