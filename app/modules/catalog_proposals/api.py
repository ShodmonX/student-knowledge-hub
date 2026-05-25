from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.catalog_proposals.schemas import (
    CatalogReportCreate,
    FacultyProposalBulkCreate,
    FacultyProposalCreate,
    SubjectProposalBulkCreate,
    SubjectProposalCreate,
    UniversityProposalCreate,
)
from app.modules.catalog_proposals.service import CatalogProposalService
from app.modules.users.models import User

router = APIRouter()


@router.post("/universities", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_university_proposal(
    payload: UniversityProposalCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    proposal = await CatalogProposalService(session).create_university_proposal(payload, user)
    return {
        "id": proposal.id,
        "status": proposal.status.value,
        "message": "Universitet taklifi yuborildi",
    }


@router.post("/faculties", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_faculty_proposal(
    payload: FacultyProposalCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    proposal = await CatalogProposalService(session).create_faculty_proposal(payload, user)
    return {
        "id": proposal.id,
        "status": proposal.status.value,
        "message": "Fakultet taklifi yuborildi",
    }


@router.post("/faculties/bulk", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_faculty_proposals_bulk(
    payload: FacultyProposalBulkCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    service = CatalogProposalService(session)
    results = []
    errors = []
    for item in payload.faculties:
        try:
            proposal = await service.create_faculty_proposal(item, user)
            results.append({"name": item.name, "id": proposal.id, "status": proposal.status.value})
        except Exception as exc:
            errors.append({"name": item.name, "error": str(exc)})
    return {
        "created": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
    }


@router.post("/subjects", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_subject_proposal(
    payload: SubjectProposalCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    proposal = await CatalogProposalService(session).create_subject_proposal(payload, user)
    return {
        "id": proposal.id,
        "status": proposal.status.value,
        "message": "Fan taklifi yuborildi",
    }


@router.post("/subjects/bulk", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_subject_proposals_bulk(
    payload: SubjectProposalBulkCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    service = CatalogProposalService(session)
    results = []
    errors = []
    for item in payload.subjects:
        try:
            proposal = await service.create_subject_proposal(item, user)
            results.append({"name": item.name, "id": proposal.id, "status": proposal.status.value})
        except Exception as exc:
            errors.append({"name": item.name, "error": str(exc)})
    return {
        "created": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
    }


@router.post("/reports", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_catalog_report(
    payload: CatalogReportCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    report = await CatalogProposalService(session).create_catalog_report(payload, user)
    return {
        "id": report.id,
        "status": str(report.status),
        "message": "Shikoyat muvaffaqiyatli qabul qilindi",
    }

