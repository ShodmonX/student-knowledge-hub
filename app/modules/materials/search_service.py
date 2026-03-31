from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.materials.enums import MaterialStatus
from app.modules.materials.repositories import MaterialRepository
from app.modules.materials.schemas import MaterialListQuery


class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.materials = MaterialRepository(session)

    async def list_public(self, query: MaterialListQuery):
        query.status = MaterialStatus.APPROVED
        statement = self.materials.build_filtered_query()
        statement = self.materials.apply_filters(statement, query)
        return await self.materials.list_filtered(statement, query.page, query.page_size)
