from enum import StrEnum


class FileKind(StrEnum):
    IMAGE = "image"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    OTHER = "other"
