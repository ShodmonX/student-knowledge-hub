from datetime import datetime

from pydantic import BaseModel

from app.modules.materials.enums import ReportStatus
from app.shared.schemas.summary import MaterialSummary, PublicUserSummary


class ModeratorScopeCreate(BaseModel):
    university_id: str | None = None
    faculty_id: str | None = None
    subject_id: str | None = None


class MaterialReportRead(BaseModel):
    id: str
    reason: str
    details: str | None
    status: ReportStatus
    resolution_note: str | None
    reviewed_at: datetime | None
    created_at: datetime
    reporter: PublicUserSummary
    material: MaterialSummary
