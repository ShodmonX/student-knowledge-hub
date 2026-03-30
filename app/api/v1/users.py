from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.auth import get_current_user
from app.models.catalog_proposal import FacultyProposal, SubjectProposal, UniversityProposal
from app.models.user import User
from app.schemas.catalog_proposal import CatalogProposalRead, HomeUniversityUpdateRequest, HomeUniversityUpdateResponse
from app.schemas.auth import ChangePasswordRequest
from app.schemas.material import MaterialListQuery, MaterialRead
from app.schemas.preferences import UserPreferenceRead, UserPreferenceUpdate
from app.schemas.user import PublicUserRead, UserRead, UserUpdateMe
from app.services.material_service import MaterialService
from app.services.user_service import UserService
from app.services.catalog_proposal_service import CatalogProposalService
from app.utils.serializers import build_catalog_proposal_read, build_material_read, build_public_user_summary

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


@router.post("/me/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await UserService(session).change_password(user, payload)
    return {"message": "Password changed"}


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


@router.post("/me/saved-materials/{material_id}")
async def save_material(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await UserService(session).save_material(material_id, user)
    return {"message": "Material saved"}


@router.delete("/me/saved-materials/{material_id}")
async def remove_saved_material(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await UserService(session).remove_saved_material(material_id, user)
    return {"message": "Saved material removed"}


@router.delete("/me/saved-materials")
async def clear_saved_materials(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await UserService(session).clear_saved_materials(user)
    return {"message": "Saved materials cleared"}
