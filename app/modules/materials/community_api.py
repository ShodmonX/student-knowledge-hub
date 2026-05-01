from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.community.schemas import CommentCreate, CommentRead, RatingCreate, RatingSummary
from app.modules.community.service import CommunityService
from app.modules.materials.common import OptionalUser, serialize_materials
from app.modules.materials.schemas import MaterialRead
from app.modules.materials.service import MaterialService
from app.modules.users.models import User
from app.shared.schemas.common import MessageResponse
from app.utils.serializers import build_comment_read

router = APIRouter()


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
    user: OptionalUser,
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


@router.delete("/{material_id}/rating", response_model=MessageResponse)
async def unrate_material(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    await CommunityService(session).unrate(material_id, user)
    return MessageResponse(message="Reyting o'chirildi")


@router.post("/{material_id}/tags/{tag_id}", response_model=MaterialRead)
async def attach_material_tag(
    material_id: str,
    tag_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.attach_tag(material_id, tag_id, user)
    return (await serialize_materials(service, [material], user))[0]


@router.delete("/{material_id}/tags/{tag_id}", response_model=MaterialRead)
async def detach_material_tag(
    material_id: str,
    tag_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.detach_tag(material_id, tag_id, user)
    return (await serialize_materials(service, [material], user))[0]
