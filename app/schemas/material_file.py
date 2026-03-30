from pydantic import BaseModel, Field

from app.enums.file_kind import FileKind
from app.schemas.common import ORMModel


class MaterialFileOrderInput(BaseModel):
    file_order: int = Field(ge=0)


class MaterialFileReorderRequest(BaseModel):
    file_ids: list[str] = Field(min_length=1)


class MaterialFileSelectionUpdate(BaseModel):
    cover: bool | None = None
    primary: bool | None = None


class AcceptedFileFormatsResponse(BaseModel):
    accepted_extensions: list[str]
    image_extensions: list[str]
    document_extensions: list[str]
    max_file_size: int
    max_total_size: int
    max_file_count: int


class MaterialFileRead(ORMModel):
    id: str
    material_id: str
    storage_key: str | None = None
    preview_storage_key: str | None = None
    original_filename: str
    mime_type: str
    file_size: int
    file_ext: str
    file_kind: FileKind
    file_order: int
    checksum_hash: str | None = None
    is_previewable: bool
    preview_page_count: int | None = None
