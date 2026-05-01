from typing import Annotated

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.admin.schemas import AdminUserUpdate, ModeratorScopeCreate
from app.modules.admin.service import AdminService
from app.modules.auth.dependencies import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.modules.users.schemas import UserRead
from app.shared.schemas.common import MessageResponse

router = APIRouter()


@router.get("/users", response_model=dict)
async def list_users(
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    q: str | None = None,
    role: str | None = None,
    status: bool | None = None,
    university_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    items, total = await AdminService(session).list_users(
        q,
        role,
        status,
        university_id,
        page,
        page_size,
    )
    return {
        "items": [UserRead.model_validate(item).model_dump() for item in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/users/{user_id}", response_model=UserRead)
async def get_user(
    user_id: str,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRead:
    user = await AdminService(session).get_user_detail(user_id)
    return UserRead.model_validate(user)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    user = await AdminService(session).update_user(
        user_id,
        payload.model_dump(exclude_unset=True),
        actor=admin,
    )
    return UserRead.model_validate(user).model_dump()


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    is_active: bool = Body(..., embed=True),
) -> dict:
    user = await AdminService(session).set_user_status(user_id, is_active, actor=admin)
    return UserRead.model_validate(user).model_dump()


@router.patch("/users/{user_id}/verify")
async def verify_user(
    user_id: str,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    is_verified: bool = Body(True, embed=True),
) -> dict:
    user = await AdminService(session).verify_user(user_id, is_verified)
    return UserRead.model_validate(user).model_dump()


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    role: UserRole,
    admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    user = await AdminService(session).update_user_role(user_id, role, actor=admin)
    return {"id": user.id, "role": user.role.value}


@router.post("/users/{user_id}/moderator-scopes")
async def assign_scope(
    user_id: str,
    payload: ModeratorScopeCreate,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    return await AdminService(session).add_moderator_scope(user_id, payload)


@router.get("/users/{user_id}/moderator-scopes")
async def list_user_scopes(
    user_id: str,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    return await AdminService(session).list_moderator_scopes(user_id)


@router.delete("/users/{user_id}/moderator-scopes/{scope_id}", response_model=MessageResponse)
async def delete_user_scope(
    user_id: str,
    scope_id: str,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    await AdminService(session).delete_moderator_scope(user_id, scope_id)
    return MessageResponse(message="Moderator scope o'chirildi")


@router.get("/moderators/scopes")
async def list_all_scopes(
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    return await AdminService(session).list_all_moderator_scopes()
