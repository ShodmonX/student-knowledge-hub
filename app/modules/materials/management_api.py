from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.materials.schemas import (
    MaterialCreate,
    MaterialFileReorderRequest,
    MaterialFileSelectionUpdate,
    MaterialRead,
    MaterialReportCreate,
    MaterialUpdate,
)
from app.modules.users.models import User
from app.modules.materials.service import MaterialService

from app.modules.materials.common import serialize_materials

router = APIRouter()


@router.post("", response_model=MaterialRead)
async def create_material(
    payload: MaterialCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.create_draft(payload, user)
    return (await serialize_materials(service, [material]))[0]


@router.post("/{material_id}/files", response_model=list[dict])
async def attach_files(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    files: list[UploadFile] = File(...),
    file_orders: list[int] = Form(...),
) -> list[dict]:
    attached = await MaterialService(session).attach_files(material_id, user, files, file_orders)
    return [
        {
            "id": item.id,
            "original_filename": item.original_filename,
            "file_order": item.file_order,
            "checksum_hash": item.checksum_hash,
        }
        for item in attached
    ]


@router.delete("/{material_id}/files/{file_id}", response_model=MaterialRead)
async def delete_material_file(
    material_id: str,
    file_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.delete_file(material_id, file_id, user)
    return (await serialize_materials(service, [material], user))[0]


@router.patch("/{material_id}/files/reorder", response_model=list[dict])
async def reorder_material_files(
    material_id: str,
    payload: MaterialFileReorderRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    files = await MaterialService(session).reorder_files(material_id, payload.file_ids, user)
    return [
        {
            "id": item.id,
            "file_order": item.file_order,
            "original_filename": item.original_filename,
        }
        for item in files
    ]


@router.patch("/{material_id}/files/{file_id}", response_model=MaterialRead)
async def update_material_file_selection(
    material_id: str,
    file_id: str,
    payload: MaterialFileSelectionUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.update_file_selection(material_id, file_id, payload.cover, payload.primary, user)
    return (await serialize_materials(service, [material], user))[0]


@router.post("/{material_id}/submit", response_model=MaterialRead)
async def submit_material(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.submit(material_id, user)
    return (await serialize_materials(service, [material]))[0]


@router.post("/{material_id}/withdraw", response_model=MaterialRead)
async def withdraw_material(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.withdraw(material_id, user)
    return (await serialize_materials(service, [material]))[0]


@router.patch("/{material_id}", response_model=MaterialRead)
async def update_material(
    material_id: str,
    payload: MaterialUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialRead:
    service = MaterialService(session)
    material = await service.update_material(material_id, payload, user)
    return (await serialize_materials(service, [material]))[0]


@router.delete("/{material_id}")
async def delete_material(
    material_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await MaterialService(session).delete_material(material_id, user)
    return {"message": "Material deleted"}


@router.post("/{material_id}/report")
async def report_material(
    material_id: str,
    payload: MaterialReportCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await MaterialService(session).report_material(material_id, payload, user)
    return {"message": "Material reported"}
