from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.modules.materials.enums import MaterialType
from app.modules.materials.schemas import AcceptedFileFormatsResponse, MaterialRead, MaterialStatsSummary
from app.modules.materials.search_service import SearchService
from app.modules.materials.service import MaterialService
from app.utils.files import ALLOWED_EXTENSIONS, DOCUMENT_EXTENSIONS, IMAGE_EXTENSIONS

from app.modules.materials.common import (
    OptionalUser,
    get_material_response,
    material_list_query,
    serialize_materials,
    storage_download_response,
)

router = APIRouter()


@router.get("/formats", response_model=AcceptedFileFormatsResponse)
async def accepted_file_formats() -> AcceptedFileFormatsResponse:
    settings = get_settings()
    return AcceptedFileFormatsResponse(
        accepted_extensions=sorted(ALLOWED_EXTENSIONS),
        image_extensions=sorted(IMAGE_EXTENSIONS),
        document_extensions=sorted(DOCUMENT_EXTENSIONS),
        max_file_size=settings.upload_max_file_size,
        max_total_size=settings.upload_max_total_size,
        max_file_count=settings.upload_max_file_count,
    )


@router.get("", response_model=dict)
async def list_materials(
    session: Annotated[AsyncSession, Depends(get_db_session)],
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
) -> dict:
    service = MaterialService(session)
    query = material_list_query(
        q,
        subject_id,
        faculty_id,
        university_id,
        material_type,
        semester,
        status,
        file_format,
        course,
        is_public,
        only_approved,
        uploaded_by,
        download_count_gte,
        page,
        page_size,
        sort,
    )
    items, total = await service.list_public(query)
    return {
        "items": [item.model_dump() for item in await serialize_materials(service, items)],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/search", response_model=dict)
async def search_materials(
    session: Annotated[AsyncSession, Depends(get_db_session)],
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
) -> dict:
    query = material_list_query(
        q,
        subject_id,
        faculty_id,
        university_id,
        material_type,
        semester,
        status,
        file_format,
        course,
        is_public,
        only_approved,
        uploaded_by,
        download_count_gte,
        page,
        page_size,
        sort,
    )
    items, total = await SearchService(session).list_public(query)
    service = MaterialService(session)
    return {
        "items": [item.model_dump() for item in await serialize_materials(service, items)],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/featured", response_model=list[MaterialRead])
async def featured_materials(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MaterialRead]:
    service = MaterialService(session)
    return await serialize_materials(service, await service.list_featured())


@router.get("/trending", response_model=list[MaterialRead])
async def trending_materials(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MaterialRead]:
    service = MaterialService(session)
    return await serialize_materials(service, await service.list_trending())


@router.get("/stats/summary", response_model=MaterialStatsSummary)
async def material_stats_summary(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialStatsSummary:
    return MaterialStatsSummary(**(await MaterialService(session).stats_summary()))


@router.get("/sitemap.xml")
async def materials_sitemap(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    items = await MaterialService(session).list_sitemap_entries()
    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for item in items:
        body.append("<url>")
        body.append(f"<loc>{item['loc']}</loc>")
        body.append(f"<lastmod>{item['lastmod']}</lastmod>")
        body.append("</url>")
    body.append("</urlset>")
    return Response("\n".join(body), media_type="application/xml")


@router.get("/{material_id}", response_model=MaterialRead)
async def get_material(
    material_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: OptionalUser,
) -> MaterialRead:
    return await get_material_response(material_id, session, user, "id")


@router.get("/slug/{slug}", response_model=MaterialRead)
async def get_material_by_slug(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: OptionalUser,
) -> MaterialRead:
    return await get_material_response(slug, session, user, "slug")


@router.get("/{material_id}/download")
async def download_material(
    material_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: OptionalUser,
):
    download = await MaterialService(session).prepare_download(material_id, None, user, "id")
    return storage_download_response(download)


@router.get("/slug/{slug}/download")
async def download_material_by_slug(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: OptionalUser,
):
    download = await MaterialService(session).prepare_download(slug, None, user, "slug")
    return storage_download_response(download)


@router.get("/{material_id}/files/{file_id}/download")
async def download_material_file(
    material_id: str,
    file_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: OptionalUser,
):
    download = await MaterialService(session).prepare_download(material_id, file_id, user, "id")
    return storage_download_response(download)


@router.get("/slug/{slug}/files/{file_id}/download")
async def download_material_file_by_slug(
    slug: str,
    file_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: OptionalUser,
):
    download = await MaterialService(session).prepare_download(slug, file_id, user, "slug")
    return storage_download_response(download)


@router.get("/{material_id}/files/{file_id}/preview")
async def preview_material_file(
    material_id: str,
    file_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: OptionalUser,
):
    download = await MaterialService(session).prepare_preview(material_id, file_id, user, "id")
    return storage_download_response(download)


@router.get("/slug/{slug}/files/{file_id}/preview")
async def preview_material_file_by_slug(
    slug: str,
    file_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: OptionalUser,
):
    download = await MaterialService(session).prepare_preview(slug, file_id, user, "slug")
    return storage_download_response(download)


@router.get("/{material_id}/related", response_model=list[MaterialRead])
async def related_materials(
    material_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MaterialRead]:
    service = MaterialService(session)
    return await serialize_materials(service, await service.list_related(material_id))


@router.get("/{material_id}/resources", response_model=list[dict])
async def material_resources(
    material_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    files = await MaterialService(session).list_resources(material_id)
    return [
        {
            "id": file.id,
            "original_filename": file.original_filename,
            "mime_type": file.mime_type,
            "is_previewable": file.is_previewable,
            "file_order": file.file_order,
        }
        for file in files
    ]
