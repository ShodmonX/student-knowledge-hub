from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material_review_log import MaterialReviewLog


class MaterialReviewLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, log: MaterialReviewLog) -> MaterialReviewLog:
        self.session.add(log)
        await self.session.flush()
        return log
