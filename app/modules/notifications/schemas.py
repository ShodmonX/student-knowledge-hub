from datetime import datetime

from app.shared.schemas.common import ORMModel


class NotificationRead(ORMModel):
    id: str
    title: str
    body: str
    is_read: bool
    created_at: datetime
