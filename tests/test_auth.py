import io

import pytest
from fastapi import UploadFile
from sqlalchemy import func, select

from app.core.exceptions import ConflictError
from app.core.security import create_access_token, hash_password
from app.enums.material_status import MaterialStatus
from app.enums.material_type import MaterialType
from app.enums.user_role import UserRole
from app.models.faculty import Faculty
from app.models.subject import Subject
from app.models.university import University
from app.models.user import User
from app.schemas.faculty import FacultyCreate
from app.schemas.material import MaterialCreate
from app.schemas.subject import SubjectCreate
from app.schemas.university import UniversityCreate
from app.services.catalog_service import CatalogService
from app.services.material_service import MaterialService
from app.services.seed_service import seed
from app.utils.slug import slugify


async def _seed_university(session):
    university = University(name="Test University", slug=slugify("Test University"))
    session.add(university)
    await session.commit()
    await session.refresh(university)
    return university


async def _seed_faculty(session, university_id: str, name: str = "Computer Science"):
    faculty = Faculty(name=name, slug=slugify(name), university_id=university_id)
    session.add(faculty)
    await session.commit()
    await session.refresh(faculty)
    return faculty


async def _seed_subject(session, faculty_id: str, name: str = "Algorithms", semester: int = 3):
    subject = Subject(
        faculty_id=faculty_id,
        name=name,
        slug=slugify(name),
        semester=semester,
        description=None,
        code=None,
    )
    session.add(subject)
    await session.commit()
    await session.refresh(subject)
    return subject


async def _seed_user(
    session,
    university_id: str,
    email: str = "user@example.com",
    role: UserRole = UserRole.STUDENT,
):
    user = User(
        full_name="Test User",
        email=email,
        hashed_password=hash_password("password123"),
        role=role,
        university_id=university_id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _access_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


def _png_upload(filename: str, color_seed: bytes) -> UploadFile:
    content = b"\x89PNG\r\n\x1a\n" + color_seed + b"test-payload"
    return UploadFile(filename=filename, file=io.BytesIO(content))


@pytest.mark.asyncio
async def test_register_and_login(client, session):
    university = await _seed_university(session)
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "password": "password123",
            "university_id": university.id,
        },
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "password123"},
    )
    assert login_response.status_code == 200
    assert "access_token" in login_response.json()


@pytest.mark.asyncio
async def test_refresh_token_rotation_revokes_reuse(client, session):
    university = await _seed_university(session)
    await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "John Doe",
            "email": "john@example.com",
            "password": "password123",
            "university_id": university.id,
        },
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "john@example.com", "password": "password123"},
    )
    assert login_response.status_code == 200
    original_refresh = login_response.json()["refresh_token"]

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert refresh_response.status_code == 200
    rotated_refresh = refresh_response.json()["refresh_token"]
    assert rotated_refresh != original_refresh

    reused_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert reused_response.status_code == 401

    revoked_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": rotated_refresh},
    )
    assert revoked_response.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_university_slug_returns_conflict(client, session):
    await _seed_university(session)

    with pytest.raises(ConflictError):
        await CatalogService(session).create_university(
            UniversityCreate(
                name="Test University",
                slug=slugify("Test University"),
            )
        )


@pytest.mark.asyncio
async def test_duplicate_faculty_name_in_same_university_returns_conflict(session):
    university = await _seed_university(session)
    await _seed_faculty(session, university.id, "Computer Science")

    with pytest.raises(ConflictError):
        await CatalogService(session).create_faculty(
            FacultyCreate(
                university_id=university.id,
                name="computer science",
                slug="cs-alt",
            )
        )


@pytest.mark.asyncio
async def test_duplicate_subject_name_in_same_semester_returns_conflict(session):
    university = await _seed_university(session)
    faculty = await _seed_faculty(session, university.id, "Engineering")
    await _seed_subject(session, faculty.id, "Algorithms", 3)

    with pytest.raises(ConflictError):
        await CatalogService(session).create_subject(
            SubjectCreate(
                faculty_id=faculty.id,
                name="algorithms",
                slug="algorithms-alt",
                semester=3,
                code=None,
                description=None,
            )
        )


@pytest.mark.asyncio
async def test_same_subject_name_in_different_semester_is_allowed(session):
    university = await _seed_university(session)
    faculty = await _seed_faculty(session, university.id, "Engineering")
    await _seed_subject(session, faculty.id, "Algorithms", 3)

    subject = await CatalogService(session).create_subject(
        SubjectCreate(
            faculty_id=faculty.id,
            name="Algorithms",
            slug="algorithms-semester-4",
            semester=4,
            code=None,
            description=None,
        )
    )
    assert subject.semester == 4


@pytest.mark.asyncio
async def test_material_slugs_are_unique_on_create(session):
    university = await _seed_university(session)
    faculty = await _seed_faculty(session, university.id, "Engineering")
    subject = await _seed_subject(session, faculty.id, "Algorithms", 3)
    user = await _seed_user(session, university.id)
    service = MaterialService(session)

    first = await service.create_draft(
        MaterialCreate(
            title="Linear Algebra Notes",
            description=None,
            material_type=MaterialType.NOTES,
            subject_id=subject.id,
            cover_file_id=None,
            primary_file_id=None,
        ),
        user,
    )
    second = await service.create_draft(
        MaterialCreate(
            title="Linear Algebra Notes",
            description=None,
            material_type=MaterialType.NOTES,
            subject_id=subject.id,
            cover_file_id=None,
            primary_file_id=None,
        ),
        user,
    )

    assert first.slug == "linear-algebra-notes"
    assert second.slug == "linear-algebra-notes-2"


@pytest.mark.asyncio
async def test_material_sitemap_uses_material_slug(session):
    university = await _seed_university(session)
    faculty = await _seed_faculty(session, university.id, "Engineering")
    subject = await _seed_subject(session, faculty.id, "Algorithms", 3)
    user = await _seed_user(session, university.id, "sitemap@example.com")
    service = MaterialService(session)
    material = await service.create_draft(
        MaterialCreate(
            title="Operating Systems Summary",
            description=None,
            material_type=MaterialType.NOTES,
            subject_id=subject.id,
            cover_file_id=None,
            primary_file_id=None,
        ),
        user,
    )
    material.status = MaterialStatus.APPROVED
    session.add(material)
    await session.commit()

    items = await service.list_sitemap_entries()
    assert any(item["loc"].endswith(f"/materials/{material.slug}") for item in items)


@pytest.mark.asyncio
async def test_public_material_list_and_search_force_approved_only(client, session):
    university = await _seed_university(session)
    faculty = await _seed_faculty(session, university.id, "Engineering")
    subject = await _seed_subject(session, faculty.id, "Algorithms", 3)
    user = await _seed_user(session, university.id, "pending@example.com")
    material = await MaterialService(session).create_draft(
        MaterialCreate(
            title="Pending Material",
            description=None,
            material_type=MaterialType.NOTES,
            subject_id=subject.id,
            cover_file_id=None,
            primary_file_id=None,
        ),
        user,
    )
    material.status = MaterialStatus.PENDING_REVIEW
    session.add(material)
    await session.commit()

    list_response = await client.get("/api/v1/materials", params={"status": "pending_review"})
    search_response = await client.get("/api/v1/materials/search", params={"status": "pending_review"})

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0
    assert list_response.json()["items"] == []
    assert search_response.status_code == 200
    assert search_response.json()["total"] == 0
    assert search_response.json()["items"] == []


@pytest.mark.asyncio
async def test_forgot_password_does_not_return_reset_token(client, session):
    university = await _seed_university(session)
    await _seed_user(session, university.id, "forgot@example.com")

    response = await client.post("/api/v1/auth/forgot-password", json={"email": "forgot@example.com"})

    assert response.status_code == 200
    assert response.json() == {"message": "If the account exists, reset instructions have been generated."}


@pytest.mark.asyncio
async def test_nonapproved_material_access_context_is_restricted_for_unauthenticated_user(session):
    university = await _seed_university(session)
    faculty = await _seed_faculty(session, university.id, "Engineering")
    subject = await _seed_subject(session, faculty.id, "Algorithms", 3)
    user = await _seed_user(session, university.id, "restricted@example.com")
    material = await MaterialService(session).create_draft(
        MaterialCreate(
            title="Restricted Material",
            description=None,
            material_type=MaterialType.NOTES,
            subject_id=subject.id,
            cover_file_id=None,
            primary_file_id=None,
        ),
        user,
    )

    access = await MaterialService(session).get_material_access_context(material, None)

    assert access["access_level"] == "restricted"
    assert access["can_download"] is False
    assert access["can_preview"] is False


@pytest.mark.asyncio
async def test_auth_session_endpoints_revoke_refresh_tokens(client, session):
    university = await _seed_university(session)
    await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Session User",
            "email": "sessions@example.com",
            "password": "password123",
            "university_id": university.id,
        },
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "sessions@example.com", "password": "password123"},
    )
    access_token = login_response.json()["access_token"]
    refresh_token = login_response.json()["refresh_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    sessions_response = await client.get("/api/v1/auth/sessions", headers=headers)
    assert sessions_response.status_code == 200
    assert len(sessions_response.json()) == 1
    session_id = sessions_response.json()[0]["id"]
    assert sessions_response.json()[0]["is_active"] is True

    revoke_response = await client.delete(f"/api/v1/auth/sessions/{session_id}", headers=headers)
    assert revoke_response.status_code == 200

    refresh_after_revoke = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_after_revoke.status_code == 401

    second_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "sessions@example.com", "password": "password123"},
    )
    second_access = second_login.json()["access_token"]
    second_refresh = second_login.json()["refresh_token"]
    logout_all_response = await client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {second_access}"},
    )
    assert logout_all_response.status_code == 200

    refresh_after_logout_all = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": second_refresh},
    )
    assert refresh_after_logout_all.status_code == 401


@pytest.mark.asyncio
async def test_tag_endpoints_create_and_attach_to_material(client, session):
    university = await _seed_university(session)
    faculty = await _seed_faculty(session, university.id, "Engineering")
    subject = await _seed_subject(session, faculty.id, "Algorithms", 3)
    admin = await _seed_user(session, university.id, "admin-tag@example.com", role=UserRole.ADMIN)
    student = await _seed_user(session, university.id, "student-tag@example.com")
    material = await MaterialService(session).create_draft(
        MaterialCreate(
            title="Tagged Material",
            description=None,
            material_type=MaterialType.NOTES,
            subject_id=subject.id,
            cover_file_id=None,
            primary_file_id=None,
        ),
        student,
    )

    create_response = await client.post(
        "/api/v1/tags",
        headers=_access_headers(admin),
        json={"name": "Math Tag"},
    )
    assert create_response.status_code == 201
    tag_id = create_response.json()["id"]

    attach_response = await client.post(
        f"/api/v1/materials/{material.id}/tags/{tag_id}",
        headers=_access_headers(student),
    )
    assert attach_response.status_code == 200
    assert attach_response.json()["tags"][0]["slug"] == "math-tag"

    list_response = await client.get("/api/v1/tags")
    assert list_response.status_code == 200
    assert any(item["id"] == tag_id for item in list_response.json())


@pytest.mark.asyncio
async def test_material_file_lifecycle_operations(session):
    university = await _seed_university(session)
    faculty = await _seed_faculty(session, university.id, "Engineering")
    subject = await _seed_subject(session, faculty.id, "Algorithms", 3)
    user = await _seed_user(session, university.id, "files@example.com")
    service = MaterialService(session)
    material = await service.create_draft(
        MaterialCreate(
            title="File Lifecycle",
            description=None,
            material_type=MaterialType.NOTES,
            subject_id=subject.id,
            cover_file_id=None,
            primary_file_id=None,
        ),
        user,
    )
    attached = await service.attach_files(
        material.id,
        user,
        [_png_upload("one.png", b"one"), _png_upload("two.png", b"two")],
        [0, 1],
    )

    reordered = await service.reorder_files(material.id, [attached[1].id, attached[0].id], user)
    assert [item.id for item in reordered] == [attached[1].id, attached[0].id]
    assert [item.file_order for item in reordered] == [0, 1]

    updated_material = await service.update_file_selection(material.id, attached[1].id, True, True, user)
    assert updated_material.cover_file_id == attached[1].id
    assert updated_material.primary_file_id == attached[1].id

    updated_material = await service.delete_file(material.id, attached[0].id, user)
    assert updated_material.file_count == 1
    assert updated_material.total_size > 0
    assert len(updated_material.files) == 1
    assert updated_material.files[0].file_order == 0


@pytest.mark.asyncio
async def test_seed_only_runs_when_database_has_no_universities(session):
    await seed()
    await session.rollback()

    university_count = await session.scalar(select(func.count(University.id)))
    faculty_count = await session.scalar(select(func.count(Faculty.id)))
    subject_count = await session.scalar(select(func.count(Subject.id)))
    user_count = await session.scalar(select(func.count(User.id)))

    assert university_count == 1
    assert faculty_count == 3
    assert subject_count == 9
    assert user_count == 1

    await seed()
    await session.rollback()

    university_count_after = await session.scalar(select(func.count(University.id)))
    faculty_count_after = await session.scalar(select(func.count(Faculty.id)))
    subject_count_after = await session.scalar(select(func.count(Subject.id)))
    user_count_after = await session.scalar(select(func.count(User.id)))

    assert university_count_after == 1
    assert faculty_count_after == 3
    assert subject_count_after == 9
    assert user_count_after == 1
