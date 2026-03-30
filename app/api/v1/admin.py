from typing import Annotated

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.auth import require_roles
from app.enums.report_status import ReportStatus
from app.enums.user_role import UserRole
from app.schemas.faculty import FacultyCreate, FacultyRead, FacultyUpdate
from app.schemas.moderator_scope import ModeratorScopeCreate
from app.schemas.report import MaterialReportRead
from app.schemas.subject import SubjectCreate, SubjectRead, SubjectUpdate
from app.schemas.university import UniversityCreate, UniversityRead, UniversityUpdate
from app.schemas.user import UserRead
from app.services.admin_service import AdminService
from app.services.catalog_service import CatalogService
from app.utils.serializers import build_audit_log_read, build_report_read

router = APIRouter()


@router.post("/universities", response_model=UniversityRead)
async def create_university(
    payload: UniversityCreate,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UniversityRead:
    item = await CatalogService(session).create_university(payload)
    return UniversityRead.model_validate(item)


@router.patch("/universities/{university_id}", response_model=UniversityRead)
async def update_university(
    university_id: str,
    payload: UniversityUpdate,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UniversityRead:
    item = await CatalogService(session).update_university(university_id, payload)
    return UniversityRead.model_validate(item)


@router.delete("/universities/{university_id}")
async def delete_university(
    university_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await CatalogService(session).delete_university(university_id)
    return {"message": "University deleted"}


@router.post("/faculties", response_model=FacultyRead)
async def create_faculty(
    payload: FacultyCreate,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FacultyRead:
    item = await CatalogService(session).create_faculty(payload)
    return FacultyRead.model_validate(item)


@router.patch("/faculties/{faculty_id}", response_model=FacultyRead)
async def update_faculty(
    faculty_id: str,
    payload: FacultyUpdate,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FacultyRead:
    item = await CatalogService(session).update_faculty(faculty_id, payload)
    return FacultyRead.model_validate(item)


@router.delete("/faculties/{faculty_id}")
async def delete_faculty(
    faculty_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await CatalogService(session).delete_faculty(faculty_id)
    return {"message": "Faculty deleted"}


@router.post("/subjects", response_model=SubjectRead)
async def create_subject(
    payload: SubjectCreate,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubjectRead:
    item = await CatalogService(session).create_subject(payload)
    return SubjectRead.model_validate(item)


@router.patch("/subjects/{subject_id}", response_model=SubjectRead)
async def update_subject(
    subject_id: str,
    payload: SubjectUpdate,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubjectRead:
    item = await CatalogService(session).update_subject(subject_id, payload)
    return SubjectRead.model_validate(item)


@router.delete("/subjects/{subject_id}")
async def delete_subject(
    subject_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await CatalogService(session).delete_subject(subject_id)
    return {"message": "Subject deleted"}


@router.get("/users", response_model=dict)
async def list_users(
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    q: str | None = None,
    role: str | None = None,
    status: bool | None = None,
    university_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    items, total = await AdminService(session).list_users(q, role, status, university_id, page, page_size)
    return {
        "items": [UserRead.model_validate(item).model_dump() for item in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/users/{user_id}", response_model=UserRead)
async def get_user(
    user_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRead:
    user = await AdminService(session).get_user_detail(user_id)
    return UserRead.model_validate(user)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: dict = Body(...),
) -> dict:
    user = await AdminService(session).update_user(user_id, payload)
    return UserRead.model_validate(user).model_dump()


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    is_active: bool = Body(..., embed=True),
) -> dict:
    user = await AdminService(session).set_user_status(user_id, is_active)
    return UserRead.model_validate(user).model_dump()


@router.patch("/users/{user_id}/verify")
async def verify_user(
    user_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    is_verified: bool = Body(True, embed=True),
) -> dict:
    user = await AdminService(session).verify_user(user_id, is_verified)
    return UserRead.model_validate(user).model_dump()


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    role: UserRole,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    user = await AdminService(session).update_user_role(user_id, role)
    return {"id": user.id, "role": user.role.value}


@router.post("/users/{user_id}/moderator-scopes")
async def assign_scope(
    user_id: str,
    payload: ModeratorScopeCreate,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    return await AdminService(session).add_moderator_scope(user_id, payload)


@router.get("/users/{user_id}/moderator-scopes")
async def list_user_scopes(
    user_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    return await AdminService(session).list_moderator_scopes(user_id)


@router.delete("/users/{user_id}/moderator-scopes/{scope_id}")
async def delete_user_scope(
    user_id: str,
    scope_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await AdminService(session).delete_moderator_scope(user_id, scope_id)
    return {"message": "Moderator scope deleted"}


@router.get("/moderators/scopes")
async def list_all_scopes(
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    return await AdminService(session).list_all_moderator_scopes()


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
