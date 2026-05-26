from __future__ import annotations

import asyncio
import hashlib
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import UploadFile

from app.core.config import get_settings
from app.core.exceptions import ResourceNotFound, ValidationAppError
from app.modules.materials.enums import FileKind
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


@dataclass
class StorageDownload:
    local_path: Path | None = None
    redirect_url: str | None = None


class BaseStorageProvider(ABC):
    @abstractmethod
    async def save(self, file: UploadFile, material_id: str, max_file_size: int) -> StoredFile:
        raise NotImplementedError

    @abstractmethod
    async def save_bytes(self, content: bytes, storage_key: str, content_type: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, storage_key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def resolve_for_download(self, storage_key: str) -> StorageDownload:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, storage_key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def read_bytes(self, storage_key: str) -> bytes:
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

    async def save_bytes(self, content: bytes, storage_key: str, content_type: str | None = None) -> None:
        destination = self.root / storage_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

    async def delete(self, storage_key: str) -> None:
        target = self.root / storage_key
        if target.exists():
            target.unlink()

    async def resolve_for_download(self, storage_key: str) -> StorageDownload:
        target = self.root / storage_key
        if not target.exists():
            raise ResourceNotFound("File not found in storage")
        return StorageDownload(local_path=target)

    async def exists(self, storage_key: str) -> bool:
        return (self.root / storage_key).exists()

    async def read_bytes(self, storage_key: str) -> bytes:
        target = self.root / storage_key
        if not target.exists():
            raise ResourceNotFound("File not found in storage")
        return target.read_bytes()


class SpacesStorageProvider(BaseStorageProvider):
    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        presigned_expiry_seconds: int,
    ) -> None:
        self.bucket = bucket
        self.presigned_expiry_seconds = presigned_expiry_seconds
        self.client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    async def save(self, file: UploadFile, material_id: str, max_file_size: int) -> StoredFile:
        extension = get_extension(file.filename or "")
        filename = f"{uuid4()}.{extension}" if extension else str(uuid4())
        storage_key = f"materials/{material_id}/{filename}"

        total_size = 0
        hasher = hashlib.sha256()
        header = bytearray()
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_path = Path(temp_file.name)
        try:
            with temp_file as output:
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
            temp_path.unlink(missing_ok=True)
            raise
        finally:
            await file.seek(0)

        if total_size == 0:
            temp_path.unlink(missing_ok=True)
            raise ValidationAppError("Empty file is not allowed")

        try:
            file_kind, mime_type = validate_file_signature(extension, bytes(header), temp_path)
            await asyncio.to_thread(
                partial(
                    self.client.upload_file,
                    str(temp_path),
                    self.bucket,
                    storage_key,
                    ExtraArgs={"ContentType": mime_type},
                )
            )
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        finally:
            temp_path.unlink(missing_ok=True)

        return StoredFile(
            storage_key=storage_key,
            file_size=total_size,
            checksum_hash=hasher.hexdigest(),
            file_kind=file_kind,
            mime_type=mime_type,
            file_ext=extension,
        )

    async def save_bytes(self, content: bytes, storage_key: str, content_type: str | None = None) -> None:
        await asyncio.to_thread(
            partial(
                self.client.put_object,
                Bucket=self.bucket,
                Key=storage_key,
                Body=content,
                ContentType=content_type or "application/octet-stream",
            )
        )

    async def delete(self, storage_key: str) -> None:
        await asyncio.to_thread(partial(self.client.delete_object, Bucket=self.bucket, Key=storage_key))

    async def resolve_for_download(self, storage_key: str) -> StorageDownload:
        try:
            url = await asyncio.to_thread(
                partial(
                    self.client.generate_presigned_url,
                    "get_object",
                    Params={
                        "Bucket": self.bucket,
                        "Key": storage_key,
                        "ResponseContentDisposition": "attachment",
                    },
                    ExpiresIn=self.presigned_expiry_seconds,
                )
            )
        except (ClientError, BotoCoreError) as exc:
            raise ResourceNotFound("File not found in storage") from exc
        return StorageDownload(redirect_url=url)

    async def exists(self, storage_key: str) -> bool:
        try:
            await asyncio.to_thread(partial(self.client.head_object, Bucket=self.bucket, Key=storage_key))
        except ClientError:
            return False
        return True

    async def read_bytes(self, storage_key: str) -> bytes:
        try:
            response = await asyncio.to_thread(
                partial(self.client.get_object, Bucket=self.bucket, Key=storage_key)
            )
        except (ClientError, BotoCoreError) as exc:
            raise ResourceNotFound("File not found in storage") from exc
        body = response["Body"]
        return await asyncio.to_thread(body.read)


class StorageService:
    def __init__(self) -> None:
        settings = get_settings()
        backend = settings.storage_backend.lower()
        if backend == "s3":
            required = {
                "s3_bucket": settings.s3_bucket,
                "s3_region": settings.s3_region,
                "s3_endpoint_url": settings.s3_endpoint_url,
                "s3_access_key_id": settings.s3_access_key_id,
                "s3_secret_access_key": settings.s3_secret_access_key,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise RuntimeError(f"S3 storage is not fully configured: {', '.join(missing)}")
            self.provider: BaseStorageProvider = SpacesStorageProvider(
                bucket=settings.s3_bucket or "",
                region=settings.s3_region or "",
                endpoint_url=settings.s3_endpoint_url or "",
                access_key_id=settings.s3_access_key_id or "",
                secret_access_key=settings.s3_secret_access_key or "",
                presigned_expiry_seconds=settings.s3_presigned_expiry_seconds,
            )
        else:
            self.provider = LocalStorageProvider(settings.storage_root)

    async def save(self, file: UploadFile, material_id: str, max_file_size: int | None = None) -> StoredFile:
        settings = get_settings()
        return await self.provider.save(file, material_id, max_file_size or settings.upload_max_file_size)

    async def save_bytes(self, content: bytes, storage_key: str, content_type: str | None = None) -> None:
        await self.provider.save_bytes(content, storage_key, content_type)

    async def delete(self, storage_key: str) -> None:
        await self.provider.delete(storage_key)

    async def delete_many(self, keys: list[str]) -> None:
        for key in keys:
            await self.delete(key)

    async def resolve_for_download(self, storage_key: str) -> StorageDownload:
        return await self.provider.resolve_for_download(storage_key)

    async def exists(self, storage_key: str) -> bool:
        return await self.provider.exists(storage_key)

    async def read_bytes(self, storage_key: str) -> bytes:
        return await self.provider.read_bytes(storage_key)
