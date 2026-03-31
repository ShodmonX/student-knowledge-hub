from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.catalog.schemas import FacultyRead, SubjectRead
from app.modules.catalog.service import CatalogService

router = APIRouter()


@router.get("/{faculty_id}", response_model=FacultyRead)
async def get_faculty(
    faculty_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FacultyRead:
    item = await CatalogService(session).get_faculty(faculty_id)
    return FacultyRead.model_validate(item)


@router.get("/{faculty_id}/subjects", response_model=list[SubjectRead])
async def list_faculty_subjects(
    faculty_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[SubjectRead]:
    items = await CatalogService(session).list_subjects(faculty_id)
    return [SubjectRead.model_validate(item) for item in items]
