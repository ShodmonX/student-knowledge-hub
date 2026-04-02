from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.admin.schemas import BackupListResponse, BackupRead, BackupRestoreResponse
from app.modules.admin.service import AdminService
from app.modules.auth.dependencies import require_roles
from app.modules.users.enums import UserRole

router = APIRouter()


@router.get("/backups", response_model=BackupListResponse)
async def list_backups(
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BackupListResponse:
    items = await AdminService(session).list_backups()
    return BackupListResponse(items=items, total=len(items))


@router.get("/backups/{backup_id}", response_model=BackupRead)
async def get_backup(
    backup_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BackupRead:
    return await AdminService(session).get_backup(backup_id)


@router.post("/backups", response_model=BackupRead)
async def create_backup(
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BackupRead:
    return await AdminService(session).create_backup()


@router.post("/backups/{backup_id}/restore", response_model=BackupRestoreResponse)
async def restore_backup(
    backup_id: str,
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BackupRestoreResponse:
    return await AdminService(session).restore_backup(backup_id)
