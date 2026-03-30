from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ResourceNotFound
from app.models.faculty import Faculty
from app.models.subject import Subject
from app.models.university import University
from app.repositories.faculty_repository import FacultyRepository
from app.repositories.subject_repository import SubjectRepository
from app.repositories.university_repository import UniversityRepository
from app.schemas.faculty import FacultyCreate, FacultyUpdate
from app.schemas.subject import SubjectCreate, SubjectUpdate
from app.schemas.university import UniversityCreate, UniversityUpdate
from app.utils.slug import slugify


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.universities = UniversityRepository(session)
        self.faculties = FacultyRepository(session)
        self.subjects = SubjectRepository(session)

    async def list_universities(self) -> list[University]:
        return await self.universities.list_all()

    async def get_university(self, university_id: str) -> University:
        university = await self.universities.get(university_id)
        if not university:
            raise ResourceNotFound("University not found")
        return university

    async def list_faculties(self, university_id: str) -> list[Faculty]:
        if not await self.universities.get(university_id):
            raise ResourceNotFound("University not found")
        return await self.faculties.list_by_university(university_id)

    async def get_faculty(self, faculty_id: str) -> Faculty:
        faculty = await self.faculties.get(faculty_id)
        if not faculty:
            raise ResourceNotFound("Faculty not found")
        return faculty

    async def list_subjects(self, faculty_id: str) -> list[Subject]:
        if not await self.faculties.get(faculty_id):
            raise ResourceNotFound("Faculty not found")
        return await self.subjects.list_by_faculty(faculty_id)

    async def get_subject(self, subject_id: str) -> Subject:
        subject = await self.subjects.get(subject_id)
        if not subject:
            raise ResourceNotFound("Subject not found")
        return subject

    async def create_university(self, payload: UniversityCreate) -> University:
        slug = payload.slug or slugify(payload.name)
        await self._ensure_university_name_available(payload.name)
        await self._ensure_university_slug_available(slug)
        university = University(name=payload.name, slug=slug)
        try:
            await self.universities.create(university)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("University with this slug already exists") from exc
        return university

    async def create_faculty(self, payload: FacultyCreate) -> Faculty:
        if not await self.universities.get(payload.university_id):
            raise ResourceNotFound("University not found")
        slug = payload.slug or slugify(payload.name)
        await self._ensure_faculty_name_available(payload.university_id, payload.name)
        await self._ensure_faculty_slug_available(payload.university_id, slug)
        faculty = Faculty(
            university_id=payload.university_id,
            name=payload.name,
            slug=slug,
        )
        try:
            await self.faculties.create(faculty)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Faculty with this slug already exists in the university") from exc
        return faculty

    async def create_subject(self, payload: SubjectCreate) -> Subject:
        if not await self.faculties.get(payload.faculty_id):
            raise ResourceNotFound("Faculty not found")
        slug = payload.slug or slugify(payload.name)
        await self._ensure_subject_name_available(payload.faculty_id, payload.name, payload.semester)
        await self._ensure_subject_slug_available(payload.faculty_id, slug, payload.semester)
        subject = Subject(
            faculty_id=payload.faculty_id,
            name=payload.name,
            slug=slug,
            code=payload.code,
            semester=payload.semester,
            description=payload.description,
        )
        try:
            await self.subjects.create(subject)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Subject with this slug already exists in the faculty and semester") from exc
        return subject

    async def update_university(self, university_id: str, payload: UniversityUpdate) -> University:
        university = await self.get_university(university_id)
        if payload.name is not None:
            await self._ensure_university_name_available(payload.name, exclude_id=university.id)
            university.name = payload.name
        if payload.slug is not None:
            await self._ensure_university_slug_available(payload.slug, exclude_id=university.id)
            university.slug = payload.slug
        elif payload.name is not None:
            slug = slugify(payload.name)
            await self._ensure_university_slug_available(slug, exclude_id=university.id)
            university.slug = slug
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("University with this slug already exists") from exc
        return university

    async def delete_university(self, university_id: str) -> None:
        university = await self.get_university(university_id)
        await self.session.delete(university)
        await self.session.commit()

    async def update_faculty(self, faculty_id: str, payload: FacultyUpdate) -> Faculty:
        faculty = await self.get_faculty(faculty_id)
        target_university_id = payload.university_id or faculty.university_id
        target_name = payload.name or faculty.name
        await self._ensure_faculty_name_available(target_university_id, target_name, exclude_id=faculty.id)
        if payload.university_id is not None:
            faculty.university_id = payload.university_id
        if payload.name is not None:
            faculty.name = payload.name
        if payload.slug is not None:
            await self._ensure_faculty_slug_available(
                target_university_id,
                payload.slug,
                exclude_id=faculty.id,
            )
            faculty.slug = payload.slug
        elif payload.name is not None:
            slug = slugify(payload.name)
            await self._ensure_faculty_slug_available(
                target_university_id,
                slug,
                exclude_id=faculty.id,
            )
            faculty.slug = slug
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Faculty with this slug already exists in the university") from exc
        return faculty

    async def delete_faculty(self, faculty_id: str) -> None:
        faculty = await self.get_faculty(faculty_id)
        await self.session.delete(faculty)
        await self.session.commit()

    async def update_subject(self, subject_id: str, payload: SubjectUpdate) -> Subject:
        subject = await self.get_subject(subject_id)
        target_faculty_id = payload.faculty_id or subject.faculty_id
        target_semester = payload.semester or subject.semester
        target_name = payload.name or subject.name
        await self._ensure_subject_name_available(
            target_faculty_id,
            target_name,
            target_semester,
            exclude_id=subject.id,
        )
        for field, value in payload.model_dump(exclude_unset=True).items():
            if field == "slug" and value is None and payload.name:
                continue
            setattr(subject, field, value)
        if payload.slug is None and payload.name:
            new_slug = slugify(payload.name)
            await self._ensure_subject_slug_available(
                target_faculty_id,
                new_slug,
                target_semester,
                exclude_id=subject.id,
            )
            subject.slug = new_slug
        elif payload.slug is not None:
            await self._ensure_subject_slug_available(
                target_faculty_id,
                payload.slug,
                target_semester,
                exclude_id=subject.id,
            )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Subject with this slug already exists in the faculty and semester") from exc
        return subject

    async def delete_subject(self, subject_id: str) -> None:
        subject = await self.get_subject(subject_id)
        await self.session.delete(subject)
        await self.session.commit()

    async def _ensure_university_slug_available(self, slug: str, exclude_id: str | None = None) -> None:
        statement = select(University.id).where(University.slug == slug)
        if exclude_id:
            statement = statement.where(University.id != exclude_id)
        result = await self.session.execute(statement)
        if result.scalar_one_or_none():
            raise ConflictError("University with this slug already exists")

    async def _ensure_university_name_available(self, name: str, exclude_id: str | None = None) -> None:
        statement = select(University.id).where(
            func.lower(func.trim(University.name)) == self._normalize_name(name)
        )
        if exclude_id:
            statement = statement.where(University.id != exclude_id)
        result = await self.session.execute(statement)
        if result.scalar_one_or_none():
            raise ConflictError("University with this name already exists")

    async def _ensure_faculty_slug_available(
        self,
        university_id: str,
        slug: str,
        exclude_id: str | None = None,
    ) -> None:
        statement = select(Faculty.id).where(
            Faculty.university_id == university_id,
            Faculty.slug == slug,
        )
        if exclude_id:
            statement = statement.where(Faculty.id != exclude_id)
        result = await self.session.execute(statement)
        if result.scalar_one_or_none():
            raise ConflictError("Faculty with this slug already exists in the university")

    async def _ensure_faculty_name_available(
        self,
        university_id: str,
        name: str,
        exclude_id: str | None = None,
    ) -> None:
        statement = select(Faculty.id).where(
            Faculty.university_id == university_id,
            func.lower(func.trim(Faculty.name)) == self._normalize_name(name),
        )
        if exclude_id:
            statement = statement.where(Faculty.id != exclude_id)
        result = await self.session.execute(statement)
        if result.scalar_one_or_none():
            raise ConflictError("Faculty with this name already exists in the university")

    async def _ensure_subject_slug_available(
        self,
        faculty_id: str,
        slug: str,
        semester: int,
        exclude_id: str | None = None,
    ) -> None:
        statement = select(Subject.id).where(
            Subject.faculty_id == faculty_id,
            Subject.slug == slug,
            Subject.semester == semester,
        )
        if exclude_id:
            statement = statement.where(Subject.id != exclude_id)
        result = await self.session.execute(statement)
        if result.scalar_one_or_none():
            raise ConflictError("Subject with this slug already exists in the faculty and semester")

    async def _ensure_subject_name_available(
        self,
        faculty_id: str,
        name: str,
        semester: int,
        exclude_id: str | None = None,
    ) -> None:
        statement = select(Subject.id).where(
            Subject.faculty_id == faculty_id,
            Subject.semester == semester,
            func.lower(func.trim(Subject.name)) == self._normalize_name(name),
        )
        if exclude_id:
            statement = statement.where(Subject.id != exclude_id)
        result = await self.session.execute(statement)
        if result.scalar_one_or_none():
            raise ConflictError("Subject with this name already exists in the faculty and semester")

    @staticmethod
    def _normalize_name(name: str) -> str:
        return name.strip().lower()
