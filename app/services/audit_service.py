from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(
        self,
        action: str,
        entity: str,
        actor: User | None = None,
        entity_id: str | None = None,
        details: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_id=actor.id if actor else None,
            entity=entity,
            entity_id=entity_id,
            action=action,
            details=details,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry
