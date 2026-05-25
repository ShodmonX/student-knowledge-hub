import io
import hashlib
import hmac
import json
import time
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import UploadFile
from pypdf import PdfWriter

from app.core.security import create_access_token, hash_password
from app.modules.materials.enums import MaterialStatus, MaterialType, ReportStatus
from app.modules.users.enums import UserRole
from app.modules.admin.scope_models import (
    ModeratorFacultyScope,
    ModeratorSubjectScope,
    ModeratorUniversityScope,
)
from app.modules.catalog.models import Faculty, Subject, University
from app.modules.materials.models import MaterialReport
from app.modules.users.models import User
from app.modules.materials.schemas import MaterialCreate
from app.modules.materials.service import MaterialService
from app.utils.slug import slugify


async def seed_university(session, name: str = "Test University") -> University:
    university = University(name=name, slug=slugify(name))
    session.add(university)
    await session.commit()
    await session.refresh(university)
    return university


async def seed_faculty(session, university_id: str, name: str = "Computer Science") -> Faculty:
    faculty = Faculty(name=name, slug=slugify(name), university_id=university_id)
    session.add(faculty)
    await session.commit()
    await session.refresh(faculty)
    return faculty


async def seed_subject(
    session,
    faculty_id: str,
    name: str = "Algorithms",
    semester: int = 3,
) -> Subject:
    subject = Subject(
        faculty_id=faculty_id,
        name=name,
        slug=slugify(name),
        description=None,
        code=None,
    )
    session.add(subject)
    await session.commit()
    await session.refresh(subject)
    return subject


async def seed_user(
    session,
    university_id: str,
    email: str = "user@example.com",
    role: UserRole = UserRole.STUDENT,
    full_name: str = "Test User",
) -> User:
    user = User(
        full_name=full_name,
        email=email,
        hashed_password=hash_password("password123"),
        role=role,
        university_id=university_id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def access_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


def internal_headers(
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    service_name: str = "telegram-bot",
    secret: str = "test-internal-secret",
    timestamp: int | None = None,
) -> dict[str, str]:
    raw_body = b""
    if payload is not None:
        raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ts = str(timestamp or int(time.time()))
    body_hash = hashlib.sha256(raw_body).hexdigest()
    canonical = "\n".join([service_name, ts, method.upper(), path, body_hash])
    signature = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "X-Internal-Service-Name": service_name,
        "X-Request-Timestamp": ts,
        "X-Signature": signature,
    }


def png_upload(filename: str, color_seed: bytes) -> UploadFile:
    content = b"\x89PNG\r\n\x1a\n" + color_seed + b"test-payload"
    return UploadFile(filename=filename, file=io.BytesIO(content))


def pdf_upload(filename: str = "preview.pdf", pages: int = 3) -> UploadFile:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return UploadFile(filename=filename, file=buffer)


def docx_upload(filename: str = "document.docx") -> UploadFile:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", "<w:document></w:document>")
    buffer.seek(0)
    return UploadFile(filename=filename, file=buffer)


def empty_upload(filename: str = "empty.png") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(b""))


async def seed_material(
    session,
    user: User,
    subject_id: str,
    title: str,
    status: MaterialStatus = MaterialStatus.DRAFT,
    material_type: MaterialType = MaterialType.NOTES,
    semesters: list[int] | None = None,
):
    material = await MaterialService(session).create_draft(
        MaterialCreate(
            title=title,
            description=None,
            material_type=material_type,
            subject_id=subject_id,
            semesters=semesters or [1],
            cover_file_id=None,
            primary_file_id=None,
        ),
        user,
    )
    if status != MaterialStatus.DRAFT:
        material.status = status
        session.add(material)
        await session.commit()
        await session.refresh(material)
    return material


async def seed_report(
    session,
    material_id: str,
    reporter_id: str,
    reason: str = "spam",
    details: str | None = "Needs review",
    status: ReportStatus = ReportStatus.OPEN,
) -> MaterialReport:
    report = MaterialReport(
        material_id=material_id,
        reporter_id=reporter_id,
        reason=reason,
        details=details,
        status=status,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report


async def add_university_scope(session, user_id: str, university_id: str) -> ModeratorUniversityScope:
    scope = ModeratorUniversityScope(user_id=user_id, university_id=university_id)
    session.add(scope)
    await session.commit()
    await session.refresh(scope)
    return scope


async def add_faculty_scope(session, user_id: str, faculty_id: str) -> ModeratorFacultyScope:
    scope = ModeratorFacultyScope(user_id=user_id, faculty_id=faculty_id)
    session.add(scope)
    await session.commit()
    await session.refresh(scope)
    return scope


async def add_subject_scope(session, user_id: str, subject_id: str) -> ModeratorSubjectScope:
    scope = ModeratorSubjectScope(user_id=user_id, subject_id=subject_id)
    session.add(scope)
    await session.commit()
    await session.refresh(scope)
    return scope
