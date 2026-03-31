from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.catalog.schemas import FacultyRead, UniversityRead
from app.modules.catalog.service import CatalogService

router = APIRouter()


@router.get("", response_model=list[UniversityRead])
async def list_universities(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[UniversityRead]:
    items = await CatalogService(session).list_universities()
    return [UniversityRead.model_validate(item) for item in items]


@router.get("/{university_id}", response_model=UniversityRead)
async def get_university(
    university_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UniversityRead:
    item = await CatalogService(session).get_university(university_id)
    return UniversityRead.model_validate(item)


@router.get("/{university_id}/faculties", response_model=list[FacultyRead])
async def list_university_faculties(
    university_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[FacultyRead]:
    items = await CatalogService(session).list_faculties(university_id)
    return [FacultyRead.model_validate(item) for item in items]
