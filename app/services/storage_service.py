from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.exceptions import ResourceNotFound, ValidationAppError
from app.enums.file_kind import FileKind
from app.utils.files import get_extension, validate_file_signature

READ_CHUNK_SIZE = 1024 * 1024
SIGNATURE_BUFFER_SIZE = 4096


@dataclass
class StoredFile:
    storage_key: str
    file_size: int
    checksum_hash: str
    file_kind: FileKind
    mime_type: str
    file_ext: str


class BaseStorageProvider(ABC):
    @abstractmethod
    async def save(self, file: UploadFile, material_id: str, max_file_size: int) -> StoredFile:
        raise NotImplementedError

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def open_for_download(self, storage_key: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        raise NotImplementedError


class LocalStorageProvider(BaseStorageProvider):
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, file: UploadFile, material_id: str, max_file_size: int) -> StoredFile:
        extension = get_extension(file.filename or "")
        filename = f"{uuid4()}.{extension}" if extension else str(uuid4())
        storage_key = f"materials/{material_id}/{filename}"
        destination = self.root / storage_key
        destination.parent.mkdir(parents=True, exist_ok=True)

        total_size = 0
        hasher = hashlib.sha256()
        header = bytearray()

        try:
            with destination.open("wb") as output:
                while chunk := await file.read(READ_CHUNK_SIZE):
                    total_size += len(chunk)
                    if total_size > max_file_size:
                        raise ValidationAppError("File too large")
                    if len(header) < SIGNATURE_BUFFER_SIZE:
                        remaining = SIGNATURE_BUFFER_SIZE - len(header)
                        header.extend(chunk[:remaining])
                    hasher.update(chunk)
                    output.write(chunk)
        except Exception:
            if destination.exists():
                destination.unlink()
            raise
        finally:
            await file.seek(0)

        if total_size == 0:
            if destination.exists():
                destination.unlink()
            raise ValidationAppError("Empty file is not allowed")

        try:
            file_kind, mime_type = validate_file_signature(extension, bytes(header), destination)
        except Exception:
            if destination.exists():
                destination.unlink()
            raise

        return StoredFile(
            storage_key=storage_key,
            file_size=total_size,
            checksum_hash=hasher.hexdigest(),
            file_kind=file_kind,
            mime_type=mime_type,
            file_ext=extension,
        )

    def delete(self, storage_key: str) -> None:
        target = self.root / storage_key
        if target.exists():
            target.unlink()

    def open_for_download(self, storage_key: str) -> Path:
        target = self.root / storage_key
        if not target.exists():
            raise ResourceNotFound("File not found in storage")
        return target

    def exists(self, storage_key: str) -> bool:
        return (self.root / storage_key).exists()


class StorageService:
    def __init__(self) -> None:
        settings = get_settings()
        self.provider: BaseStorageProvider = LocalStorageProvider(settings.storage_root)

    async def save(self, file: UploadFile, material_id: str, max_file_size: int) -> StoredFile:
        return await self.provider.save(file, material_id, max_file_size)

    def delete(self, storage_key: str) -> None:
        self.provider.delete(storage_key)

    def delete_many(self, keys: list[str]) -> None:
        for key in keys:
            self.delete(key)

    def open_for_download(self, storage_key: str) -> Path:
        return self.provider.open_for_download(storage_key)

    def exists(self, storage_key: str) -> bool:
        return self.provider.exists(storage_key)
