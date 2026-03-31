from typing import Annotated

from fastapi import Depends
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.materials.enums import MaterialType
from app.modules.auth.dependencies import get_optional_user
from app.modules.materials.schemas import MaterialListQuery, MaterialRead
from app.modules.users.models import User
from app.infrastructure.storage.service import StorageDownload
from app.modules.materials.service import MaterialService
from app.utils.serializers import build_material_read


def material_list_query(
    q: str | None = None,
    subject_id: str | None = None,
    faculty_id: str | None = None,
    university_id: str | None = None,
    material_type: MaterialType | None = None,
    semester: int | None = None,
    status: str | None = None,
    file_format: str | None = None,
    course: int | None = None,
    is_public: bool | None = None,
    only_approved: bool | None = None,
    uploaded_by: str | None = None,
    download_count_gte: int | None = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_at_desc",
) -> MaterialListQuery:
    return MaterialListQuery(
        q=q,
        subject_id=subject_id,
        faculty_id=faculty_id,
        university_id=university_id,
        material_type=material_type,
        semester=semester,
        status=status,
        file_format=file_format,
        course=course,
        is_public=is_public,
        only_approved=only_approved,
        uploaded_by=uploaded_by,
        download_count_gte=download_count_gte,
        page=page,
        page_size=page_size,
        sort=sort,
    )


async def serialize_materials(
    service: MaterialService,
    materials: list,
    user: User | None = None,
) -> list[MaterialRead]:
    ratings = await service.get_rating_snapshot([material.id for material in materials])
    serialized: list[MaterialRead] = []
    for material in materials:
        access = await service.get_material_access_context(material, user)
        serialized.append(
            build_material_read(
                material,
                average_rating=ratings.get(material.id, (0.0, 0))[0],
                rating_count=ratings.get(material.id, (0.0, 0))[1],
                access_level=access["access_level"],
                can_download=access["can_download"],
                can_preview=access["can_preview"],
                requires_auth_for_download=access["requires_auth_for_download"],
                preview_page_limit=access["preview_page_limit"],
                include_sensitive_file_fields=False,
            )
        )
    return serialized


async def get_material_response(
    identifier: str,
    session: AsyncSession,
    user: User | None,
    lookup_field: str,
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.get_material_for_view(identifier, user, lookup_field)
    return (await serialize_materials(service, [material], user))[0]


def storage_download_response(download: StorageDownload):
    if download.redirect_url:
        return RedirectResponse(download.redirect_url, status_code=307)
    if download.local_path:
        return FileResponse(download.local_path)
    raise RuntimeError("Storage download target is not available")


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
