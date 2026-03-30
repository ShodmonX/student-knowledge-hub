from pydantic import BaseModel, Field

from app.enums.file_kind import FileKind
from app.schemas.common import ORMModel


class MaterialFileOrderInput(BaseModel):
    file_order: int = Field(ge=0)


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
    storage_key: str
    original_filename: str
    mime_type: str
    file_size: int
    file_ext: str
    file_kind: FileKind
    file_order: int
    checksum_hash: str
    is_previewable: bool
