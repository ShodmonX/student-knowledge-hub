import pytest

from app.models.faculty import Faculty
from app.models.subject import Subject
from app.core.exceptions import ConflictError
from app.models.university import University
from app.schemas.faculty import FacultyCreate
from app.schemas.subject import SubjectCreate
from app.schemas.university import UniversityCreate
from app.services.catalog_service import CatalogService
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
