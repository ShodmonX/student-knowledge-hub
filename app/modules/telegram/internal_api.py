from typing import Annotated

from datetime import datetime
import mimetypes
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ResourceNotFound, ValidationAppError
from app.infrastructure.storage.service import StorageService
from app.modules.users.schemas import UserRead
from app.modules.users.service import UserService

from app.core.security_controls import AuthRateLimiter
from app.db.session import get_db_session
from app.modules.auth.dependencies import require_internal_service
from app.modules.telegram.event_service import TelegramEventService
from app.modules.telegram.schemas import (
    TelegramIdentityLookupResponse,
    TelegramInternalConsumeRequest,
    TelegramInternalLinkResponse,
    TelegramInternalVerifyCodeRequest,
    TelegramMaterialModerationRequest,
    TelegramMaterialModerationResponse,
    TelegramMaterialRejectRequest,
    TelegramOutboxEventListResponse,
    TelegramProposalDetailResponse,
    TelegramProposalListResponse,
    TelegramProposalMessagePayload,
    TelegramProposalModerationRequest,
    TelegramProposalModerationResponse,
    TelegramProposalRejectRequest,
    TelegramUserRegistrationMessagePayload,
)
from app.modules.moderation.schemas import RejectRequest
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


@router.delete("/link/{telegram_user_id}", response_model=TelegramInternalLinkResponse)
async def unlink_telegram_account_by_telegram_user_id(
    telegram_user_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramInternalLinkResponse:
    return await TelegramService(session).unlink_by_telegram_user_id(telegram_user_id)


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


@router.post("/moderation/materials/{material_id}/approve", response_model=TelegramMaterialModerationResponse)
async def approve_material(
    material_id: str,
    payload: TelegramMaterialModerationRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramMaterialModerationResponse:
    return await TelegramService(session).approve_material(material_id, payload.telegram_user_id)


@router.post("/moderation/materials/{material_id}/reject", response_model=TelegramMaterialModerationResponse)
async def reject_material(
    material_id: str,
    payload: TelegramMaterialRejectRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramMaterialModerationResponse:
    return await TelegramService(session).reject_material(
        material_id,
        payload.telegram_user_id,
        RejectRequest(reason=payload.reason, note=payload.note),
    )


@router.post("/moderation/materials/{material_id}/request-revision", response_model=TelegramMaterialModerationResponse)
async def request_material_revision(
    material_id: str,
    payload: TelegramMaterialRejectRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramMaterialModerationResponse:
    return await TelegramService(session).request_material_revision(
        material_id,
        payload.telegram_user_id,
        RejectRequest(reason=payload.reason, note=payload.note),
    )


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


@router.post("/users/{telegram_user_id}/avatar", response_model=UserRead)
async def upload_telegram_avatar(
    telegram_user_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    file: UploadFile = File(...),
) -> UserRead:
    identity = await TelegramService(session).get_identity_by_telegram_user_id(telegram_user_id)
    if not identity.is_linked or not identity.platform_user:
        raise ResourceNotFound("Telegramga bog'langan foydalanuvchi topilmadi")
        
    user_id = identity.platform_user.id
    user = await UserService(session).get_user(user_id)
    if not user:
        raise ResourceNotFound("Foydalanuvchi topilmadi")

    filename = file.filename or ""
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in ["jpg", "jpeg", "png"]:
        raise ValidationAppError("Faqat rasm formatidagi fayllar ruxsat etiladi (.jpg, .jpeg, .png)")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise ValidationAppError("Rasm hajmi 5MB dan oshmasligi kerak")
    
    storage = StorageService()
    
    for old_ext in ["jpg", "jpeg", "png"]:
        old_key = f"avatars/{user.id}/avatar.{old_ext}"
        if await storage.exists(old_key):
            await storage.delete(old_key)

    storage_key = f"avatars/{user.id}/avatar.{ext}"
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or "image/jpeg"
    await storage.save_bytes(content, storage_key, content_type)

    user.avatar_url = f"/api/v1/users/{user.id}/avatar?v={int(datetime.now().timestamp())}"
    await session.commit()
    await session.refresh(user)

    return UserRead.model_validate(user)


__all__ = ["router"]
