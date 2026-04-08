from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.telegram.schemas import TelegramLinkActionRead, TelegramLinkSessionRead, TelegramLinkStatusRead
from app.modules.telegram.service import TelegramService
from app.modules.users.models import User

router = APIRouter()


@router.post("/users/me/telegram-link-sessions", response_model=TelegramLinkSessionRead, status_code=status.HTTP_201_CREATED)
async def create_telegram_link_session(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramLinkSessionRead:
    return await TelegramService(session).create_link_session(user)


@router.get("/users/me/telegram-link", response_model=TelegramLinkStatusRead)
async def get_telegram_link_status(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramLinkStatusRead:
    return await TelegramService(session).get_link_status(user)


@router.delete("/users/me/telegram-link", response_model=TelegramLinkActionRead)
async def unlink_telegram_account(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelegramLinkActionRead:
    result = await TelegramService(session).unlink(user)
    return TelegramLinkActionRead(**result)


__all__ = ["router"]
