from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.catalog_proposal import (
    FacultyProposalCreate,
    UniversityProposalCreate,
    SubjectProposalCreate,
)
from app.services.catalog_proposal_service import CatalogProposalService

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
        "message": "University proposal submitted successfully",
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
        "message": "Faculty proposal submitted successfully",
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
        "message": "Subject proposal submitted successfully",
    }
