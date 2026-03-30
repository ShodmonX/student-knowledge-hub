from pydantic import BaseModel


class ModeratorScopeCreate(BaseModel):
    university_id: str | None = None
    faculty_id: str | None = None
    subject_id: str | None = None
