from pydantic import BaseModel

from app.modules.materials.enums import RejectReason


class RejectRequest(BaseModel):
    reason: RejectReason
    note: str | None = None


class MoveSubjectRequest(BaseModel):
    subject_id: str
    note: str | None = None
