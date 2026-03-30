from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.university import University


class UniversityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[University]:
        result = await self.session.execute(select(University).order_by(University.name.asc()))
        return list(result.scalars().all())

    async def get(self, university_id: str) -> University | None:
        return await self.session.get(University, university_id)

    async def create(self, university: University) -> University:
        self.session.add(university)
        await self.session.flush()
        await self.session.refresh(university)
        return university
