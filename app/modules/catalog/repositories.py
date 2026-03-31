from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Faculty, Subject, University


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
