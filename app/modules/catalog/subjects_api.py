from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.catalog.schemas import SubjectRead
from app.modules.catalog.service import CatalogService
from app.modules.materials.schemas import MaterialListQuery
from app.modules.materials.service import MaterialService
from app.utils.serializers import build_material_read

router = APIRouter()


@router.get("/{subject_id}", response_model=SubjectRead)
async def get_subject(
    subject_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubjectRead:
    subject = await CatalogService(session).get_subject(subject_id)
    return SubjectRead.model_validate(subject)


@router.get("/{subject_id}/materials", response_model=dict)
async def subject_materials(
    subject_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: int = 1,
    page_size: int = 20,
) -> dict:
    query = MaterialListQuery(subject_id=subject_id, page=page, page_size=page_size)
    service = MaterialService(session)
    items, total = await service.list_public(query)
    ratings = await service.get_rating_snapshot([item.id for item in items])
    return {
        "items": [
            build_material_read(
                item,
                average_rating=ratings.get(item.id, (0.0, 0))[0],
                rating_count=ratings.get(item.id, (0.0, 0))[1],
            ).model_dump()
            for item in items
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }
