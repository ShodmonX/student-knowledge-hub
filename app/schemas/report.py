from datetime import datetime

from pydantic import BaseModel

from app.enums.report_status import ReportStatus
from app.schemas.summary import MaterialSummary, PublicUserSummary


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
