from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.auth import require_roles
from app.enums.user_role import UserRole
from app.schemas.tag import TagCreate, TagRead, TagUpdate
from app.services.tag_service import TagService

router = APIRouter()


@router.get("", response_model=list[TagRead])
async def list_tags(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[TagRead]:
    return [TagRead.model_validate(item) for item in await TagService(session).list_tags()]


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(
    payload: TagCreate,
    _: Annotated[object, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TagRead:
    return TagRead.model_validate(await TagService(session).create_tag(payload))


@router.patch("/{tag_id}", response_model=TagRead)
async def update_tag(
    tag_id: str,
    payload: TagUpdate,
    _: Annotated[object, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TagRead:
    return TagRead.model_validate(await TagService(session).update_tag(tag_id, payload))


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    await TagService(session).delete_tag(tag_id)
