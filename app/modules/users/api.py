from typing import Annotated

from datetime import datetime
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ResourceNotFound, ValidationAppError
from app.infrastructure.storage.service import StorageService
import mimetypes

from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import ChangePasswordRequest
from app.modules.catalog_proposals.models import (
    FacultyProposal,
    SubjectProposal,
    UniversityProposal,
)
from app.modules.catalog_proposals.schemas import (
    CatalogProposalRead,
    HomeUniversityUpdateRequest,
    HomeUniversityUpdateResponse,
)
from app.modules.catalog_proposals.service import CatalogProposalService
from app.modules.materials.schemas import MaterialListQuery, MaterialRead
from app.modules.materials.service import MaterialService
from app.modules.users.models import User
from app.modules.users.schemas import (
    PublicUserRead,
    UserPreferenceRead,
    UserPreferenceUpdate,
    UserRead,
    UserUpdateMe,
)
from app.modules.users.service import UserService
from app.shared.schemas.common import MessageResponse
from app.utils.serializers import (
    build_catalog_proposal_read,
    build_material_read,
    build_public_user_summary,
)

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def me(
    user: Annotated[User, Depends(get_current_user)],
) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdateMe,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRead:
    updated = await UserService(session).update_me(user, payload)
    return UserRead.model_validate(updated)


@router.post("/me/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    await UserService(session).change_password(user, payload)
    return MessageResponse(message="Parol o'zgartirildi")


@router.patch("/me/home-university", response_model=HomeUniversityUpdateResponse)
async def update_home_university(
    payload: HomeUniversityUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> HomeUniversityUpdateResponse:
    result = await CatalogProposalService(session).update_home_university(user, payload)
    return HomeUniversityUpdateResponse(**result)


@router.get("/me/preferences", response_model=UserPreferenceRead)
async def get_preferences(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserPreferenceRead:
    preference = await UserService(session).get_preferences(user)
    return UserPreferenceRead.model_validate(preference)


@router.patch("/me/preferences", response_model=UserPreferenceRead)
async def update_preferences(
    payload: UserPreferenceUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserPreferenceRead:
    preference = await UserService(session).update_preferences(user, payload)
    return UserPreferenceRead.model_validate(preference)


@router.get("/{user_id}/public", response_model=PublicUserRead)
async def get_public_user(
    user_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PublicUserRead:
    user = await UserService(session).get_user(user_id)
    return PublicUserRead(**build_public_user_summary(user).model_dump())


@router.get("/me/materials", response_model=dict)
async def current_user_materials(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    q: str | None = None,
    status: str | None = None,
    material_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_at_desc",
) -> dict:
    query = MaterialListQuery(
        q=q,
        status=status,
        material_type=material_type,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    service = UserService(session)
    material_service = MaterialService(session)
    items, total = await service.list_user_materials(user, query)
    serialized = await material_service.get_rating_snapshot([item.id for item in items])
    return {
        "items": [
            build_material_read(
                item,
                average_rating=serialized.get(item.id, (0.0, 0))[0],
                rating_count=serialized.get(item.id, (0.0, 0))[1],
            ).model_dump()
            for item in items
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/me/catalog-proposals/universities", response_model=list[CatalogProposalRead])
async def current_user_university_proposals(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CatalogProposalRead]:
    proposals = await CatalogProposalService(session).list_user_proposals(user, UniversityProposal)
    return [build_catalog_proposal_read(item, "university", user) for item in proposals]


@router.get("/me/catalog-proposals/faculties", response_model=list[CatalogProposalRead])
async def current_user_faculty_proposals(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CatalogProposalRead]:
    proposals = await CatalogProposalService(session).list_user_proposals(user, FacultyProposal)
    return [build_catalog_proposal_read(item, "faculty", user) for item in proposals]


@router.get("/me/catalog-proposals/subjects", response_model=list[CatalogProposalRead])
async def current_user_subject_proposals(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CatalogProposalRead]:
    proposals = await CatalogProposalService(session).list_user_proposals(user, SubjectProposal)
    return [build_catalog_proposal_read(item, "subject", user) for item in proposals]


@router.get("/me/saved-materials", response_model=list[MaterialRead])
async def list_saved_materials(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MaterialRead]:
    service = UserService(session)
    material_service = MaterialService(session)
    items = await service.list_saved_materials(user)
    ratings = await material_service.get_rating_snapshot([item.id for item in items])
    return [
        build_material_read(
            item,
            average_rating=ratings.get(item.id, (0.0, 0))[0],
            rating_count=ratings.get(item.id, (0.0, 0))[1],
        )
        for item in items
    ]


@router.get("/me/downloaded-materials", response_model=list[MaterialRead])
async def list_downloaded_materials(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MaterialRead]:
    service = UserService(session)
    material_service = MaterialService(session)
    items = await service.list_downloaded_materials(user)
    ratings = await material_service.get_rating_snapshot([item.id for item in items])
    return [
        build_material_read(
            item,
            average_rating=ratings.get(item.id, (0.0, 0))[0],
            rating_count=ratings.get(item.id, (0.0, 0))[1],
        )
        for item in items
    ]


@router.post("/me/saved-materials/{material_id}", response_model=MessageResponse)
async def save_material(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    await UserService(session).save_material(material_id, user)
    return MessageResponse(message="Material saqlandi")


@router.delete("/me/saved-materials/{material_id}", response_model=MessageResponse)
async def remove_saved_material(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    await UserService(session).remove_saved_material(material_id, user)
    return MessageResponse(message="Saqlangan material o'chirildi")


@router.delete("/me/saved-materials", response_model=MessageResponse)
async def clear_saved_materials(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    await UserService(session).clear_saved_materials(user)
    return MessageResponse(message="Saqlangan materiallar tozalandi")


@router.post("/avatar", response_model=UserRead)
async def upload_avatar(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    file: UploadFile = File(...),
) -> UserRead:
    filename = file.filename or ""
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in ["jpg", "jpeg", "png"]:
        raise ValidationAppError("Faqat rasm formatidagi fayllar ruxsat etiladi (.jpg, .jpeg, .png)")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise ValidationAppError("Rasm hajmi 5MB dan oshmasligi kerak")
    
    storage = StorageService()
    
    for old_ext in ["jpg", "jpeg", "png"]:
        old_key = f"avatars/{user.id}/avatar.{old_ext}"
        if await storage.exists(old_key):
            await storage.delete(old_key)

    storage_key = f"avatars/{user.id}/avatar.{ext}"
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or "image/jpeg"
    await storage.save_bytes(content, storage_key, content_type)

    user.avatar_url = f"/api/v1/users/{user.id}/avatar?v={int(datetime.now().timestamp())}"
    await session.commit()
    await session.refresh(user)

    return UserRead.model_validate(user)


@router.delete("/avatar", response_model=UserRead)
async def delete_avatar(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRead:
    storage = StorageService()
    
    for old_ext in ["jpg", "jpeg", "png"]:
        old_key = f"avatars/{user.id}/avatar.{old_ext}"
        if await storage.exists(old_key):
            await storage.delete(old_key)

    user.avatar_url = None
    await session.commit()
    await session.refresh(user)

    return UserRead.model_validate(user)


@router.get("/{user_id}/avatar")
async def get_avatar(
    user_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    storage = StorageService()
    storage_key = None
    content_type = None
    for ext in ["png", "jpg", "jpeg"]:
        key = f"avatars/{user_id}/avatar.{ext}"
        if await storage.exists(key):
            storage_key = key
            content_type = f"image/{'png' if ext == 'png' else 'jpeg'}"
            break
            
    if not storage_key:
        raise ResourceNotFound("Avatar topilmadi")
        
    download = await storage.resolve_for_download(storage_key)
    if download.redirect_url:
        return RedirectResponse(download.redirect_url, status_code=307)
    if download.local_path:
        return FileResponse(download.local_path, media_type=content_type)
    raise ResourceNotFound("Avatar yuklab olish imkoni bo'lmadi")
