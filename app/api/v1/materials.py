from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.dependencies.auth import get_current_user, get_optional_user
from app.enums.material_type import MaterialType
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentRead
from app.schemas.material_file import AcceptedFileFormatsResponse
from app.schemas.material import (
    MaterialCreate,
    MaterialListQuery,
    MaterialRead,
    MaterialReportCreate,
    MaterialStatsSummary,
    MaterialUpdate,
)
from app.schemas.rating import RatingCreate, RatingSummary
from app.services.community_service import CommunityService
from app.services.material_service import MaterialService
from app.utils.files import ALLOWED_EXTENSIONS, DOCUMENT_EXTENSIONS, IMAGE_EXTENSIONS
from app.utils.serializers import build_comment_read, build_material_read

router = APIRouter()


def _material_list_query(
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


async def _serialize_materials(service: MaterialService, materials: list) -> list[MaterialRead]:
    ratings = await service.get_rating_snapshot([material.id for material in materials])
    return [
        build_material_read(
            material,
            average_rating=ratings.get(material.id, (0.0, 0))[0],
            rating_count=ratings.get(material.id, (0.0, 0))[1],
        )
        for material in materials
    ]


@router.post("", response_model=MaterialRead)
async def create_material(
    payload: MaterialCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.create_draft(payload, user)
    return (await _serialize_materials(service, [material]))[0]


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


@router.post("/{material_id}/files", response_model=list[dict])
async def attach_files(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    files: list[UploadFile] = File(...),
    file_orders: list[int] = Form(...),
) -> list[dict]:
    attached = await MaterialService(session).attach_files(material_id, user, files, file_orders)
    return [
        {
            "id": item.id,
            "original_filename": item.original_filename,
            "file_order": item.file_order,
            "checksum_hash": item.checksum_hash,
        }
        for item in attached
    ]


@router.post("/{material_id}/submit", response_model=MaterialRead)
async def submit_material(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.submit(material_id, user)
    return (await _serialize_materials(service, [material]))[0]


@router.post("/{material_id}/withdraw", response_model=MaterialRead)
async def withdraw_material(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.withdraw(material_id, user)
    return (await _serialize_materials(service, [material]))[0]


@router.patch("/{material_id}", response_model=MaterialRead)
async def update_material(
    material_id: str,
    payload: MaterialUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.update_material(material_id, payload, user)
    return (await _serialize_materials(service, [material]))[0]


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
    query = _material_list_query(
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
        "items": [item.model_dump() for item in await _serialize_materials(service, items)],
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
    service = MaterialService(session)
    query = _material_list_query(
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
        "items": [item.model_dump() for item in await _serialize_materials(service, items)],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/featured", response_model=list[MaterialRead])
async def featured_materials(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MaterialRead]:
    service = MaterialService(session)
    return await _serialize_materials(service, await service.list_featured())


@router.get("/trending", response_model=list[MaterialRead])
async def trending_materials(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MaterialRead]:
    service = MaterialService(session)
    return await _serialize_materials(service, await service.list_trending())


@router.get("/stats/summary", response_model=MaterialStatsSummary)
async def material_stats_summary(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialStatsSummary:
    return MaterialStatsSummary(**(await MaterialService(session).stats_summary()))


@router.get("/{material_id}", response_model=MaterialRead)
async def get_material(
    material_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: User | None = Depends(get_optional_user),
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.get_material_for_view(material_id, user)
    return (await _serialize_materials(service, [material]))[0]


@router.get("/{material_id}/download")
async def download_material(
    material_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: User | None = Depends(get_optional_user),
):
    path = await MaterialService(session).prepare_download(material_id, None, user)
    return FileResponse(path)


@router.get("/{material_id}/files/{file_id}/download")
async def download_material_file(
    material_id: str,
    file_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: User | None = Depends(get_optional_user),
):
    path = await MaterialService(session).prepare_download(material_id, file_id, user)
    return FileResponse(path)


@router.get("/{material_id}/files/{file_id}/preview")
async def preview_material_file(
    material_id: str,
    file_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: User | None = Depends(get_optional_user),
):
    path = await MaterialService(session).prepare_preview(material_id, file_id, user)
    return FileResponse(path)


@router.get("/{material_id}/related", response_model=list[MaterialRead])
async def related_materials(
    material_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MaterialRead]:
    service = MaterialService(session)
    return await _serialize_materials(service, await service.list_related(material_id))


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


@router.get("/{material_id}/comments", response_model=list[CommentRead])
async def list_material_comments(
    material_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CommentRead]:
    comments = await CommunityService(session).list_comments(material_id)
    return [build_comment_read(comment) for comment in comments]


@router.post("/{material_id}/comments", response_model=CommentRead)
async def create_material_comment(
    material_id: str,
    payload: CommentCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CommentRead:
    comment = await CommunityService(session).create_comment(material_id, payload, user)
    return build_comment_read(comment)


@router.get("/{material_id}/rating", response_model=RatingSummary)
async def material_rating_summary(
    material_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: User | None = Depends(get_optional_user),
) -> RatingSummary:
    return RatingSummary(**(await CommunityService(session).get_rating_summary(material_id, user)))


@router.post("/{material_id}/rating", response_model=RatingSummary)
async def rate_material(
    material_id: str,
    payload: RatingCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RatingSummary:
    return RatingSummary(**(await CommunityService(session).rate(material_id, payload.value, user)))


@router.delete("/{material_id}/rating")
async def unrate_material(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await CommunityService(session).unrate(material_id, user)
    return {"message": "Rating removed"}


@router.delete("/{material_id}")
async def delete_material(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await MaterialService(session).delete_material(material_id, user)
    return {"message": "Material deleted"}


@router.post("/{material_id}/report")
async def report_material(
    material_id: str,
    payload: MaterialReportCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await MaterialService(session).report_material(material_id, payload, user)
    return {"message": "Material reported"}
