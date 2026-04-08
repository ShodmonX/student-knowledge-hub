from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TelegramUserPayload(BaseModel):
    telegram_user_id: int
    username: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    language_code: str | None = Field(default=None, max_length=16)


class TelegramLinkSessionRead(BaseModel):
    session_id: str
    deep_link_url: str
    manual_code: str
    expires_at: datetime
    expires_in_seconds: int


class TelegramLinkStatusRead(BaseModel):
    is_linked: bool
    telegram_username: str | None = None
    telegram_first_name: str | None = None
    linked_at: datetime | None = None


class TelegramLinkActionRead(BaseModel):
    status: Literal["unlinked"]


class TelegramPlatformIdentity(BaseModel):
    id: str
    display_name: str
    role: str | None = None
    is_active: bool | None = None


class TelegramInternalConsumeRequest(BaseModel):
    token: str = Field(min_length=8, max_length=256)
    telegram_user: TelegramUserPayload


class TelegramInternalVerifyCodeRequest(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    telegram_user: TelegramUserPayload


class TelegramInternalLinkResponse(BaseModel):
    status: str
    platform_user: TelegramPlatformIdentity | None = None


class TelegramIdentityLookupResponse(BaseModel):
    is_linked: bool
    platform_user: TelegramPlatformIdentity | None = None


class TelegramProposalSummary(BaseModel):
    id: str
    proposal_type: str
    title: str
    status: str


class TelegramModerationActor(BaseModel):
    user_id: str
    display_name: str


class TelegramProposalDetailSubmittedBy(BaseModel):
    id: str
    display_name: str


class TelegramProposalDetailResponse(BaseModel):
    id: str
    status: str
    proposal_type: str
    title: str
    description: str | None = None
    submitted_by: TelegramProposalDetailSubmittedBy | None = None
    scope: dict[str, str | None]
    created_at: datetime


class TelegramProposalModerationRequest(BaseModel):
    telegram_user_id: int


class TelegramProposalRejectRequest(BaseModel):
    telegram_user_id: int
    reason: str = Field(min_length=2, max_length=255)


class TelegramProposalModerationResponse(BaseModel):
    status: str
    proposal: TelegramProposalSummary | None = None
    moderated_by: TelegramModerationActor | None = None
    reason: str | None = None
    processed_at: datetime | None = None


class TelegramProposalListItem(BaseModel):
    id: str
    proposal_type: str
    title: str
    created_at: datetime
    submitted_by_name: str | None = None


class TelegramProposalListResponse(BaseModel):
    items: list[TelegramProposalListItem]
    total: int
    limit: int
    offset: int


class TelegramProposalMessagePayload(BaseModel):
    proposal_id: str
    proposal_type: str
    title: str
    description: str | None = None
    submitted_by_name: str | None = None
    created_at: datetime
    approve_callback_data: str
    reject_callback_data: str


class TelegramEventRecipient(BaseModel):
    platform_user_id: str
    role: str | None = None
    telegram_user_id: int | None = None
    telegram_username: str | None = None


class TelegramOutboxEventRead(BaseModel):
    event_id: str
    event_type: str
    occurred_at: datetime
    entity_type: str | None = None
    entity_id: str | None = None
    delivery_channel: str
    recipient: TelegramEventRecipient
    payload: dict


class TelegramOutboxEventListResponse(BaseModel):
    items: list[TelegramOutboxEventRead]
    total: int
    limit: int


class TelegramUserRegistrationMessagePayload(BaseModel):
    user_id: str
    full_name: str
    email: str
    university_name: str | None = None
    registered_at: datetime
