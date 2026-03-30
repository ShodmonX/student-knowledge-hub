from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material_file import MaterialFile


class MaterialFileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_many(self, files: list[MaterialFile]) -> list[MaterialFile]:
        self.session.add_all(files)
        await self.session.flush()
        return files

    async def get(self, file_id: str) -> MaterialFile | None:
        return await self.session.get(MaterialFile, file_id)

    async def list_by_material(self, material_id: str) -> list[MaterialFile]:
        result = await self.session.execute(
            select(MaterialFile)
            .where(MaterialFile.material_id == material_id)
            .order_by(MaterialFile.file_order.asc())
        )
        return list(result.scalars().all())
