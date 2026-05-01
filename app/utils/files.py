from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile, ZipFile

from app.core.exceptions import ValidationAppError
from app.modules.materials.enums import FileKind

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
DOCUMENT_EXTENSIONS = {"pdf", "docx", "djvu"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS
PREVIEWABLE_EXTENSIONS = ALLOWED_EXTENSIONS

MIME_BY_EXTENSION = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "djvu": "image/vnd.djvu",
}


def get_extension(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


def detect_file_kind(extension: str) -> FileKind:
    if extension in IMAGE_EXTENSIONS:
        return FileKind.IMAGE
    if extension in DOCUMENT_EXTENSIONS:
        return FileKind.DOCUMENT
    return FileKind.OTHER


def detect_mime_type(extension: str) -> str:
    return MIME_BY_EXTENSION.get(extension, "application/octet-stream")


def validate_file_signature(extension: str, header: bytes, stored_path: Path) -> tuple[FileKind, str]:
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationAppError("Unsupported file type")

    if extension in {"jpg", "jpeg"}:
        if not header.startswith(b"\xff\xd8\xff"):
            raise ValidationAppError("Uploaded file content does not match JPEG signature")
    elif extension == "png":
        if not header.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValidationAppError("Uploaded file content does not match PNG signature")
    elif extension == "webp":
        if not (header.startswith(b"RIFF") and header[8:12] == b"WEBP"):
            raise ValidationAppError("Uploaded file content does not match WEBP signature")
    elif extension == "pdf":
        if not header.startswith(b"%PDF-"):
            raise ValidationAppError("Uploaded file content does not match PDF signature")
    elif extension == "djvu":
        if not header.startswith(b"AT&TFORM"):
            raise ValidationAppError("Uploaded file content does not match DJVU signature")
    elif extension == "docx":
        if not header.startswith(b"PK\x03\x04"):
            raise ValidationAppError("Uploaded file content does not match DOCX signature")
        _validate_docx_archive(stored_path)

    return detect_file_kind(extension), detect_mime_type(extension)


def _validate_docx_archive(stored_path: Path) -> None:
    try:
        with ZipFile(stored_path) as archive:
            names = set(archive.namelist())
    except BadZipFile as exc:
        raise ValidationAppError("Invalid DOCX file") from exc

    required_members = {"[Content_Types].xml", "word/document.xml"}
    if not required_members.issubset(names):
        raise ValidationAppError("Uploaded file is not a valid DOCX document")
