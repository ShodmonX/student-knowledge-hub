from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subject import Subject


class SubjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_faculty(self, faculty_id: str) -> list[Subject]:
        result = await self.session.execute(
            select(Subject).where(Subject.faculty_id == faculty_id).order_by(Subject.name.asc())
        )
        return list(result.scalars().all())

    async def get(self, subject_id: str) -> Subject | None:
        return await self.session.get(Subject, subject_id)

    async def create(self, subject: Subject) -> Subject:
        self.session.add(subject)
        await self.session.flush()
        await self.session.refresh(subject)
        return subject
