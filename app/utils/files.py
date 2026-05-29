from __future__ import annotations

import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from app.core.exceptions import ValidationAppError
from app.modules.materials.enums import FileKind

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
DOCUMENT_EXTENSIONS = {"pdf", "docx", "djvu", "pptx", "ppt", "xlsx", "xls", "ipynb", "txt", "epub"}
AUDIO_VIDEO_EXTENSIONS = {"mp3", "mp4"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS | AUDIO_VIDEO_EXTENSIONS
PREVIEWABLE_EXTENSIONS = ALLOWED_EXTENSIONS

MIME_BY_EXTENSION = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "djvu": "image/vnd.djvu",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "ipynb": "application/x-ipynb+json",
    "txt": "text/plain",
    "epub": "application/epub+zip",
    "mp3": "audio/mpeg",
    "mp4": "video/mp4",
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
    elif extension == "pptx":
        if not header.startswith(b"PK\x03\x04"):
            raise ValidationAppError("Uploaded file content does not match PPTX signature")
        _validate_pptx_archive(stored_path)
    elif extension == "ppt":
        if not header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise ValidationAppError("Uploaded file content does not match PPT signature")
    elif extension == "xlsx":
        if not header.startswith(b"PK\x03\x04"):
            raise ValidationAppError("Uploaded file content does not match XLSX signature")
        _validate_xlsx_archive(stored_path)
    elif extension == "xls":
        if not header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise ValidationAppError("Uploaded file content does not match XLS signature")
    elif extension == "epub":
        if not header.startswith(b"PK\x03\x04"):
            raise ValidationAppError("Uploaded file content does not match EPUB signature")
        _validate_epub_archive(stored_path)
    elif extension == "ipynb":
        _validate_ipynb_json(stored_path)
    elif extension == "txt":
        _validate_txt_utf8(stored_path)
    elif extension == "mp3":
        if not (header.startswith(b"ID3") or header.startswith(b"\xff\xfb") or header.startswith(b"\xff\xf3") or header.startswith(b"\xff\xf2")):
            raise ValidationAppError("Uploaded file content does not match MP3 signature")
    elif extension == "mp4":
        if b"ftyp" not in header[4:12]:
            raise ValidationAppError("Uploaded file content does not match MP4 signature")

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


def _validate_pptx_archive(stored_path: Path) -> None:
    try:
        with ZipFile(stored_path) as archive:
            names = set(archive.namelist())
    except BadZipFile as exc:
        raise ValidationAppError("Invalid PPTX file") from exc

    required_members = {"[Content_Types].xml", "ppt/presentation.xml"}
    if not required_members.issubset(names):
        raise ValidationAppError("Uploaded file is not a valid PPTX document")


def _validate_xlsx_archive(stored_path: Path) -> None:
    try:
        with ZipFile(stored_path) as archive:
            names = set(archive.namelist())
    except BadZipFile as exc:
        raise ValidationAppError("Invalid XLSX file") from exc

    required_members = {"[Content_Types].xml", "xl/workbook.xml"}
    if not required_members.issubset(names):
        raise ValidationAppError("Uploaded file is not a valid XLSX document")


def _validate_epub_archive(stored_path: Path) -> None:
    try:
        with ZipFile(stored_path) as archive:
            names = set(archive.namelist())
    except BadZipFile as exc:
        raise ValidationAppError("Invalid EPUB file") from exc

    # EPUB requires mimetype and META-INF/container.xml
    required_members = {"mimetype", "META-INF/container.xml"}
    if not required_members.issubset(names):
        raise ValidationAppError("Uploaded file is not a valid EPUB document")


def _validate_ipynb_json(stored_path: Path) -> None:
    try:
        with stored_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict) or "cells" not in data or "metadata" not in data:
                raise ValidationAppError("Uploaded file is not a valid Jupyter Notebook")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ValidationAppError("Invalid Jupyter Notebook file") from exc


def _validate_txt_utf8(stored_path: Path) -> None:
    try:
        with stored_path.open("r", encoding="utf-8") as f:
            # Read first 1000 characters to check encoding
            f.read(1000)
    except UnicodeDecodeError as exc:
        raise ValidationAppError("Uploaded TXT file must be valid UTF-8 encoded text") from exc
