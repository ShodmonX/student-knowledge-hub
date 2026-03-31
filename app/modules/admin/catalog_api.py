from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.catalog.service import CatalogService
from app.modules.auth.dependencies import require_roles
from app.modules.users.enums import UserRole
from app.modules.catalog.schemas import (
    FacultyCreate,
    FacultyRead,
    FacultyUpdate,
    SubjectCreate,
    SubjectRead,
    SubjectUpdate,
    UniversityCreate,
    UniversityRead,
    UniversityUpdate,
)

router = APIRouter()


@router.post("/universities", response_model=UniversityRead)
async def create_university(
    payload: UniversityCreate,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UniversityRead:
    item = await CatalogService(session).create_university(payload)
    return UniversityRead.model_validate(item)


@router.patch("/universities/{university_id}", response_model=UniversityRead)
async def update_university(
    university_id: str,
    payload: UniversityUpdate,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UniversityRead:
    item = await CatalogService(session).update_university(university_id, payload)
    return UniversityRead.model_validate(item)


@router.delete("/universities/{university_id}")
async def delete_university(
    university_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await CatalogService(session).delete_university(university_id)
    return {"message": "University deleted"}


@router.post("/faculties", response_model=FacultyRead)
async def create_faculty(
    payload: FacultyCreate,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FacultyRead:
    item = await CatalogService(session).create_faculty(payload)
    return FacultyRead.model_validate(item)


@router.patch("/faculties/{faculty_id}", response_model=FacultyRead)
async def update_faculty(
    faculty_id: str,
    payload: FacultyUpdate,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FacultyRead:
    item = await CatalogService(session).update_faculty(faculty_id, payload)
    return FacultyRead.model_validate(item)


@router.delete("/faculties/{faculty_id}")
async def delete_faculty(
    faculty_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await CatalogService(session).delete_faculty(faculty_id)
    return {"message": "Faculty deleted"}


@router.post("/subjects", response_model=SubjectRead)
async def create_subject(
    payload: SubjectCreate,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubjectRead:
    item = await CatalogService(session).create_subject(payload)
    return SubjectRead.model_validate(item)


@router.patch("/subjects/{subject_id}", response_model=SubjectRead)
async def update_subject(
    subject_id: str,
    payload: SubjectUpdate,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubjectRead:
    item = await CatalogService(session).update_subject(subject_id, payload)
    return SubjectRead.model_validate(item)


@router.delete("/subjects/{subject_id}")
async def delete_subject(
    subject_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await CatalogService(session).delete_subject(subject_id)
    return {"message": "Subject deleted"}
