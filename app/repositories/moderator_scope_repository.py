from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.moderator_scope import (
    ModeratorFacultyScope,
    ModeratorSubjectScope,
    ModeratorUniversityScope,
)


class ModeratorScopeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_scope(
        self,
        user_id: str,
        university_id: str | None = None,
        faculty_id: str | None = None,
        subject_id: str | None = None,
    ):
        if university_id:
            scope = ModeratorUniversityScope(user_id=user_id, university_id=university_id)
        elif faculty_id:
            scope = ModeratorFacultyScope(user_id=user_id, faculty_id=faculty_id)
        else:
            scope = ModeratorSubjectScope(user_id=user_id, subject_id=subject_id)
        self.session.add(scope)
        await self.session.flush()
        return scope

    async def list_scope_ids(self, user_id: str) -> dict[str, set[str]]:
        uni_rows = await self.session.execute(
            select(ModeratorUniversityScope.university_id).where(ModeratorUniversityScope.user_id == user_id)
        )
        faculty_rows = await self.session.execute(
            select(ModeratorFacultyScope.faculty_id).where(ModeratorFacultyScope.user_id == user_id)
        )
        subject_rows = await self.session.execute(
            select(ModeratorSubjectScope.subject_id).where(ModeratorSubjectScope.user_id == user_id)
        )
        return {
            "universities": set(uni_rows.scalars().all()),
            "faculties": set(faculty_rows.scalars().all()),
            "subjects": set(subject_rows.scalars().all()),
        }
