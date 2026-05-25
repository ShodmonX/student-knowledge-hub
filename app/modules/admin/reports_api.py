from typing import Annotated

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_roles
from app.modules.users.enums import UserRole
from app.modules.materials.enums import ReportStatus
from app.modules.admin.schemas import MaterialReportRead
from app.utils.serializers import build_audit_log_read, build_report_read, build_public_user_summary
from app.modules.admin.service import AdminService
from app.modules.catalog_proposals.schemas import (
    CatalogReportRead,
    CatalogReportResolveRequest,
    CatalogReportDismissRequest,
)
from app.modules.catalog_proposals.service import CatalogProposalService
from app.modules.users.models import User

router = APIRouter()


@router.get("/reports", response_model=dict)
async def list_reports(
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: int = 1,
    page_size: int = 20,
    status: ReportStatus | None = None,
) -> dict:
    items, total = await AdminService(session).list_reports(page, page_size, status)
    return {
        "items": [build_report_read(item).model_dump() for item in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/reports/{report_id}", response_model=MaterialReportRead)
async def get_report(
    report_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialReportRead:
    report = await AdminService(session).get_report(report_id)
    return build_report_read(report)


@router.patch("/reports/{report_id}", response_model=MaterialReportRead)
async def update_report(
    report_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: dict = Body(...),
) -> MaterialReportRead:
    report = await AdminService(session).update_report(report_id, payload)
    return build_report_read(report)


@router.post("/reports/{report_id}/resolve", response_model=MaterialReportRead)
async def resolve_report(
    report_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    resolution_note: str | None = Body(default=None, embed=True),
) -> MaterialReportRead:
    report = await AdminService(session).resolve_report(report_id, resolution_note)
    return build_report_read(report)


@router.post("/reports/{report_id}/dismiss", response_model=MaterialReportRead)
async def dismiss_report(
    report_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    resolution_note: str | None = Body(default=None, embed=True),
) -> MaterialReportRead:
    report = await AdminService(session).dismiss_report(report_id, resolution_note)
    return build_report_read(report)


@router.get("/audit-logs", response_model=dict)
async def list_audit_logs(
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor_id: str | None = None,
    entity: str | None = None,
    action: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    items, total = await AdminService(session).list_audit_logs(actor_id, entity, action, page, page_size)
    return {
        "items": [build_audit_log_read(item).model_dump() for item in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/dashboard/summary")
async def dashboard_summary(
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    return await AdminService(session).dashboard_summary()


@router.get("/dashboard/charts")
async def dashboard_charts(
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    return await AdminService(session).dashboard_charts()


@router.get("/catalog-reports", response_model=dict)
async def list_catalog_reports(
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: int = 1,
    page_size: int = 20,
    status: ReportStatus | None = None,
    entity_type: str | None = None,
) -> dict:
    items, total = await CatalogProposalService(session).list_catalog_reports(
        page=page, page_size=page_size, status=status, entity_type=entity_type
    )
    return {
        "items": [
            CatalogReportRead(
                id=item.id,
                entity_type=item.entity_type,
                entity_id=item.entity_id,
                entity_name=item.entity_name,
                reporter_id=item.reporter_id,
                reviewer_id=item.reviewer_id,
                reason=item.reason,
                details=item.details,
                status=item.status,
                resolution_note=item.resolution_note,
                reviewed_at=item.reviewed_at,
                created_at=item.created_at,
                reporter=build_public_user_summary(item.reporter),
                reviewer=build_public_user_summary(item.reviewer),
            ).model_dump()
            for item in items
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/catalog-reports/{report_id}", response_model=CatalogReportRead)
async def get_catalog_report(
    report_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CatalogReportRead:
    item = await CatalogProposalService(session).get_catalog_report(report_id)
    return CatalogReportRead(
        id=item.id,
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        entity_name=item.entity_name,
        reporter_id=item.reporter_id,
        reviewer_id=item.reviewer_id,
        reason=item.reason,
        details=item.details,
        status=item.status,
        resolution_note=item.resolution_note,
        reviewed_at=item.reviewed_at,
        created_at=item.created_at,
        reporter=build_public_user_summary(item.reporter),
        reviewer=build_public_user_summary(item.reviewer),
    )


@router.post("/catalog-reports/{report_id}/resolve", response_model=CatalogReportRead)
async def resolve_catalog_report(
    report_id: str,
    admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: CatalogReportResolveRequest = Body(...),
) -> CatalogReportRead:
    item = await CatalogProposalService(session).resolve_catalog_report(
        report_id=report_id, reviewer=admin, resolution_note=payload.resolution_note
    )
    return CatalogReportRead(
        id=item.id,
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        entity_name=item.entity_name,
        reporter_id=item.reporter_id,
        reviewer_id=item.reviewer_id,
        reason=item.reason,
        details=item.details,
        status=item.status,
        resolution_note=item.resolution_note,
        reviewed_at=item.reviewed_at,
        created_at=item.created_at,
        reporter=build_public_user_summary(item.reporter),
        reviewer=build_public_user_summary(item.reviewer),
    )


@router.post("/catalog-reports/{report_id}/dismiss", response_model=CatalogReportRead)
async def dismiss_catalog_report(
    report_id: str,
    admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: CatalogReportDismissRequest = Body(...),
) -> CatalogReportRead:
    item = await CatalogProposalService(session).dismiss_catalog_report(
        report_id=report_id, reviewer=admin, resolution_note=payload.resolution_note
    )
    return CatalogReportRead(
        id=item.id,
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        entity_name=item.entity_name,
        reporter_id=item.reporter_id,
        reviewer_id=item.reviewer_id,
        reason=item.reason,
        details=item.details,
        status=item.status,
        resolution_note=item.resolution_note,
        reviewed_at=item.reviewed_at,
        created_at=item.created_at,
        reporter=build_public_user_summary(item.reporter),
        reviewer=build_public_user_summary(item.reviewer),
    )

