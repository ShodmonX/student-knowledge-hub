from typing import Annotated

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_roles
from app.modules.users.enums import UserRole
from app.modules.materials.enums import ReportStatus
from app.modules.admin.schemas import MaterialReportRead
from app.utils.serializers import build_audit_log_read, build_report_read

from app.modules.admin.service import AdminService

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
