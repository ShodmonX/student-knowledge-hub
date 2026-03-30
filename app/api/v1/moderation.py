from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationAppError
from app.db.session import get_db_session
from app.dependencies.auth import require_roles
from app.enums.user_role import UserRole
from app.schemas.catalog_proposal import (
    CatalogProposalRead,
    ProposalApproveRequest,
    ProposalMapExistingRequest,
    ProposalRejectRequest,
)
from app.models.user import User
from app.schemas.material import MaterialRead
from app.schemas.moderation import MoveSubjectRequest, RejectRequest
from app.services.catalog_proposal_service import CatalogProposalService
from app.services.material_service import MaterialService
from app.services.moderation_service import ModerationService
from app.utils.serializers import build_catalog_proposal_read, build_material_read

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


@router.get("/catalog-proposals")
async def pending_catalog_proposals(
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    service = CatalogProposalService(session)
    items = await service.list_pending(actor)
    return {
        "universities": [build_catalog_proposal_read(item, "university") for item in items["universities"]],
        "faculties": [build_catalog_proposal_read(item, "faculty") for item in items["faculties"]],
        "subjects": [build_catalog_proposal_read(item, "subject") for item in items["subjects"]],
    }


@router.get("/catalog-proposals/universities", response_model=list[CatalogProposalRead])
async def pending_university_proposals(
    actor: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CatalogProposalRead]:
    items = await CatalogProposalService(session).list_pending(actor, "universities")
    return [build_catalog_proposal_read(item, "university") for item in items["universities"]]


@router.get("/catalog-proposals/faculties", response_model=list[CatalogProposalRead])
async def pending_faculty_proposals(
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CatalogProposalRead]:
    items = await CatalogProposalService(session).list_pending(actor, "faculties")
    return [build_catalog_proposal_read(item, "faculty") for item in items["faculties"]]


@router.get("/catalog-proposals/subjects", response_model=list[CatalogProposalRead])
async def pending_subject_proposals(
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CatalogProposalRead]:
    items = await CatalogProposalService(session).list_pending(actor, "subjects")
    return [build_catalog_proposal_read(item, "subject") for item in items["subjects"]]


@router.patch("/catalog-proposals/universities/{proposal_id}/approve", response_model=CatalogProposalRead)
async def approve_university_proposal(
    proposal_id: str,
    payload: ProposalApproveRequest,
    actor: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CatalogProposalRead:
    item = await CatalogProposalService(session).approve_university(proposal_id, actor, payload)
    return build_catalog_proposal_read(item, "university")


@router.patch("/catalog-proposals/universities/{proposal_id}/reject", response_model=CatalogProposalRead)
async def reject_university_proposal(
    proposal_id: str,
    payload: ProposalRejectRequest,
    actor: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CatalogProposalRead:
    item = await CatalogProposalService(session).reject_university(proposal_id, actor, payload)
    return build_catalog_proposal_read(item, "university")


@router.patch("/catalog-proposals/faculties/{proposal_id}/approve", response_model=CatalogProposalRead)
async def approve_faculty_proposal(
    proposal_id: str,
    payload: ProposalApproveRequest,
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CatalogProposalRead:
    item = await CatalogProposalService(session).approve_faculty(proposal_id, actor, payload)
    return build_catalog_proposal_read(item, "faculty")


@router.patch("/catalog-proposals/faculties/{proposal_id}/reject", response_model=CatalogProposalRead)
async def reject_faculty_proposal(
    proposal_id: str,
    payload: ProposalRejectRequest,
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CatalogProposalRead:
    item = await CatalogProposalService(session).reject_faculty(proposal_id, actor, payload)
    return build_catalog_proposal_read(item, "faculty")


@router.patch("/catalog-proposals/subjects/{proposal_id}/approve", response_model=CatalogProposalRead)
async def approve_subject_proposal(
    proposal_id: str,
    payload: ProposalApproveRequest,
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CatalogProposalRead:
    item = await CatalogProposalService(session).approve_subject(proposal_id, actor, payload)
    return build_catalog_proposal_read(item, "subject")


@router.patch("/catalog-proposals/subjects/{proposal_id}/reject", response_model=CatalogProposalRead)
async def reject_subject_proposal(
    proposal_id: str,
    payload: ProposalRejectRequest,
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CatalogProposalRead:
    item = await CatalogProposalService(session).reject_subject(proposal_id, actor, payload)
    return build_catalog_proposal_read(item, "subject")


@router.patch("/catalog-proposals/{proposal_type}/{proposal_id}/map-existing", response_model=CatalogProposalRead)
async def map_catalog_proposal_to_existing(
    proposal_type: str,
    proposal_id: str,
    payload: ProposalMapExistingRequest,
    actor: Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CatalogProposalRead:
    service = CatalogProposalService(session)
    if proposal_type == "universities":
        item = await service.map_existing_university(proposal_id, actor, payload.target_id, payload.note)
        return build_catalog_proposal_read(item, "university")
    if proposal_type == "faculties":
        item = await service.map_existing_faculty(proposal_id, actor, payload.target_id, payload.note)
        return build_catalog_proposal_read(item, "faculty")
    if proposal_type == "subjects":
        item = await service.map_existing_subject(proposal_id, actor, payload.target_id, payload.note)
        return build_catalog_proposal_read(item, "subject")
    raise ValidationAppError("Unsupported proposal type")
