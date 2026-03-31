from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.modules.materials.schemas import MaterialRead
from app.modules.moderation.schemas import MoveSubjectRequest, RejectRequest
from app.modules.materials.service import MaterialService
from app.utils.serializers import build_material_read

from app.modules.moderation.service import ModerationService

router = APIRouter()


@router.get("/materials/pending", response_model=list[MaterialRead])
async def pending_materials(
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MaterialRead]:
    service = ModerationService(session)
    items = await service.list_pending(actor)
    material_service = MaterialService(session)
    ratings = await material_service.get_rating_snapshot([item.id for item in items])
    return [
        build_material_read(
            item,
            average_rating=ratings.get(item.id, (0.0, 0))[0],
            rating_count=ratings.get(item.id, (0.0, 0))[1],
        )
        for item in items
    ]


@router.patch("/materials/{material_id}/approve", response_model=MaterialRead)
async def approve_material(
    material_id: str,
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    material = await ModerationService(session).approve(material_id, actor)
    return build_material_read(material)


@router.patch("/materials/{material_id}/reject", response_model=MaterialRead)
async def reject_material(
    material_id: str,
    payload: RejectRequest,
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    material = await ModerationService(session).reject(material_id, payload, actor)
    return build_material_read(material)


@router.patch("/materials/{material_id}/move-subject", response_model=MaterialRead)
async def move_subject(
    material_id: str,
    payload: MoveSubjectRequest,
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    material = await ModerationService(session).move_subject(material_id, payload, actor)
    return build_material_read(material)


@router.post("/materials/{material_id}/request-revision", response_model=MaterialRead)
async def request_revision(
    material_id: str,
    payload: RejectRequest,
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    material = await ModerationService(session).request_revision(material_id, payload, actor)
    return build_material_read(material)


@router.get("/materials/{material_id}/history")
async def moderation_history(
    material_id: str,
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    logs = await ModerationService(session).history(material_id, actor)
    return [
        {
            "id": log.id,
            "action": log.action.value,
            "actor_id": log.actor_id,
            "note": log.note,
            "reason": log.reason,
            "created_at": log.created_at,
        }
        for log in logs
    ]


@router.get("/materials/{material_id}/context")
async def moderation_context(
    material_id: str,
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    return await ModerationService(session).context(material_id, actor)
