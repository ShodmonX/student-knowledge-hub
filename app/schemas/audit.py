from datetime import datetime

from pydantic import BaseModel

from app.schemas.summary import PublicUserSummary


class AuditLogRead(BaseModel):
    id: str
    entity: str
    entity_id: str | None
    action: str
    details: str | None
    created_at: datetime
    actor: PublicUserSummary | None = None
