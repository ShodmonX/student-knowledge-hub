from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFound
from app.modules.notifications.models import Notification
from app.modules.users.models import User


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_notifications(self, user: User) -> list[Notification]:
        result = await self.session.execute(
            select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc())
        )
        return list(result.scalars().all())

    async def mark_notification_read(self, notification_id: str, user: User) -> Notification:
        notification = await self.session.get(Notification, notification_id)
        if not notification or notification.user_id != user.id:
            raise ResourceNotFound("Notification not found")
        notification.is_read = True
        await self.session.commit()
        return notification

    async def mark_all_notifications_read(self, user: User) -> int:
        notifications = await self.list_notifications(user)
        for item in notifications:
            item.is_read = True
        await self.session.commit()
        return len(notifications)
