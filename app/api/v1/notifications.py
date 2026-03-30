from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.notification import NotificationRead
from app.services.user_service import UserService

router = APIRouter()


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[NotificationRead]:
    items = await UserService(session).list_notifications(user)
    return [NotificationRead.model_validate(item) for item in items]


@router.patch("/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_read(
    notification_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NotificationRead:
    item = await UserService(session).mark_notification_read(notification_id, user)
    return NotificationRead.model_validate(item)


@router.patch("/read-all")
async def mark_all_notifications_read(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, int]:
    count = await UserService(session).mark_all_notifications_read(user)
    return {"updated": count}
