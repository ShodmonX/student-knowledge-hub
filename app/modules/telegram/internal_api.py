from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security_controls import AuthRateLimiter
from app.db.session import get_db_session
from app.modules.auth.dependencies import require_internal_service
from app.modules.telegram.event_service import TelegramEventService
from app.modules.telegram.schemas import (
    TelegramIdentityLookupResponse,
    TelegramInternalConsumeRequest,
    TelegramInternalLinkResponse,
    TelegramInternalVerifyCodeRequest,
    TelegramOutboxEventListResponse,
    TelegramProposalDetailResponse,
    TelegramProposalListResponse,
    TelegramProposalMessagePayload,
    TelegramProposalModerationRequest,
    TelegramProposalModerationResponse,
    TelegramProposalRejectRequest,
    TelegramUserRegistrationMessagePayload,
)
from app.modules.telegram.service import TelegramService

router = APIRouter(dependencies=[Depends(require_internal_service)])


@router.post("/link/consume", response_model=TelegramInternalLinkResponse)
async def consume_telegram_link_token(
    request: Request,
    payload: TelegramInternalConsumeRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramInternalLinkResponse:
    await AuthRateLimiter().check_sensitive_rate(request, payload.token, "auth.telegram.link_consume")
    return await TelegramService(session).consume_token(payload.token, payload.telegram_user)


@router.post("/link/verify-code", response_model=TelegramInternalLinkResponse)
async def verify_telegram_link_code(
    request: Request,
    payload: TelegramInternalVerifyCodeRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramInternalLinkResponse:
    await AuthRateLimiter().check_sensitive_rate(request, payload.code, "auth.telegram.code_verify")
    return await TelegramService(session).verify_code(payload.code, payload.telegram_user)


@router.get("/users/{telegram_user_id}/identity", response_model=TelegramIdentityLookupResponse)
async def get_telegram_identity(
    telegram_user_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramIdentityLookupResponse:
    return await TelegramService(session).get_identity_by_telegram_user_id(telegram_user_id)


@router.get("/moderation/proposals/{proposal_id}", response_model=TelegramProposalDetailResponse)
async def get_proposal_detail(
    proposal_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramProposalDetailResponse:
    return await TelegramService(session).get_proposal_detail(proposal_id)


@router.post("/moderation/proposals/{proposal_id}/approve", response_model=TelegramProposalModerationResponse)
async def approve_proposal(
    proposal_id: str,
    payload: TelegramProposalModerationRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramProposalModerationResponse:
    return await TelegramService(session).approve_proposal(proposal_id, payload.telegram_user_id)


@router.post("/moderation/proposals/{proposal_id}/reject", response_model=TelegramProposalModerationResponse)
async def reject_proposal(
    proposal_id: str,
    payload: TelegramProposalRejectRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramProposalModerationResponse:
    return await TelegramService(session).reject_proposal(proposal_id, payload.telegram_user_id, payload.reason)


@router.get("/moderation/proposals", response_model=TelegramProposalListResponse)
async def list_pending_proposals(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status: str = Query(default="pending"),
    proposal_type: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TelegramProposalListResponse:
    del status
    return await TelegramService(session).list_pending_proposals(proposal_type, limit, offset)


@router.get("/notifications/proposals/{proposal_id}/telegram-message", response_model=TelegramProposalMessagePayload)
async def get_proposal_message(
    proposal_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramProposalMessagePayload:
    return await TelegramService(session).get_proposal_message_payload(proposal_id)


@router.get("/notifications/users/{user_id}/telegram-message", response_model=TelegramUserRegistrationMessagePayload)
async def get_user_registration_message(
    user_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramUserRegistrationMessagePayload:
    return await TelegramService(session).get_user_registration_message_payload(user_id)


@router.get("/events", response_model=TelegramOutboxEventListResponse)
async def list_pending_events(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=100, ge=1, le=500),
) -> TelegramOutboxEventListResponse:
    return await TelegramEventService(session).list_pending_event_items(limit)


__all__ = ["router"]
