from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.faculty import Faculty


class FacultyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_university(self, university_id: str) -> list[Faculty]:
        result = await self.session.execute(
            select(Faculty).where(Faculty.university_id == university_id).order_by(Faculty.name.asc())
        )
        return list(result.scalars().all())

    async def get(self, faculty_id: str) -> Faculty | None:
        return await self.session.get(Faculty, faculty_id)

    async def create(self, faculty: Faculty) -> Faculty:
        self.session.add(faculty)
        await self.session.flush()
        await self.session.refresh(faculty)
        return faculty
