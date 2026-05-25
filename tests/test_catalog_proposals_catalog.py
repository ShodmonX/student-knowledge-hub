import pytest

from app.core.exceptions import ConflictError, ResourceNotFound, ValidationAppError
from app.modules.materials.enums import MaterialStatus
from app.modules.catalog_proposals.schemas import (
    FacultyProposalCreate,
    HomeUniversityUpdateRequest,
    SubjectProposalCreate,
    UniversityProposalCreate,
)
from app.modules.catalog.schemas import FacultyCreate, FacultyUpdate, SubjectCreate, SubjectUpdate, UniversityCreate, UniversityUpdate
from app.modules.catalog.service import CatalogService
from app.modules.catalog_proposals.service import CatalogProposalService
from tests.helpers import (
    access_headers,
    seed_faculty,
    seed_material,
    seed_subject,
    seed_university,
    seed_user,
)


@pytest.mark.asyncio
async def test_catalog_public_endpoints_cover_list_and_detail_routes(client, session):
    university = await seed_university(session, "Public University")
    faculty = await seed_faculty(session, university.id, "Public Faculty")
    subject = await seed_subject(session, faculty.id, "Public Subject", 2)
    owner = await seed_user(session, university.id, "public-owner@example.com")
    approved_material = await seed_material(
        session,
        owner,
        subject.id,
        "Approved Public Material",
        status=MaterialStatus.APPROVED,
    )
    await seed_material(
        session,
        owner,
        subject.id,
        "Pending Private Material",
        status=MaterialStatus.PENDING_REVIEW,
    )

    universities_response = await client.get("/api/v1/universities")
    university_tree_response = await client.get("/api/v1/universities/tree")
    university_response = await client.get(f"/api/v1/universities/{university.id}")
    faculties_response = await client.get(f"/api/v1/universities/{university.id}/faculties")
    faculty_response = await client.get(f"/api/v1/faculties/{faculty.id}")
    subjects_response = await client.get(f"/api/v1/faculties/{faculty.id}/subjects")
    subject_response = await client.get(f"/api/v1/subjects/{subject.id}")
    subject_materials_response = await client.get(f"/api/v1/subjects/{subject.id}/materials")

    assert universities_response.status_code == 200
    assert any(item["id"] == university.id for item in universities_response.json())
    assert university_tree_response.status_code == 200
    tree_university = next(
        item for item in university_tree_response.json() if item["id"] == university.id
    )
    assert tree_university["faculties"][0]["id"] == faculty.id
    assert tree_university["faculties"][0]["subjects"][0]["id"] == subject.id
    assert university_response.status_code == 200
    assert university_response.json()["id"] == university.id
    assert faculties_response.status_code == 200
    assert faculties_response.json()[0]["id"] == faculty.id
    assert faculty_response.status_code == 200
    assert faculty_response.json()["id"] == faculty.id
    assert subjects_response.status_code == 200
    assert subjects_response.json()[0]["id"] == subject.id
    assert subject_response.status_code == 200
    assert subject_response.json()["id"] == subject.id
    assert subject_materials_response.status_code == 200
    assert subject_materials_response.json()["total"] == 1
    assert subject_materials_response.json()["items"][0]["id"] == approved_material.id

    missing_university = await client.get("/api/v1/universities/missing-id")
    missing_faculty = await client.get("/api/v1/faculties/missing-id")
    missing_subject = await client.get("/api/v1/subjects/missing-id")
    assert missing_university.status_code == 404
    assert missing_faculty.status_code == 404
    assert missing_subject.status_code == 404


@pytest.mark.asyncio
async def test_user_catalog_proposal_endpoints_and_home_university_cooldown(client, session):
    home_university = await seed_university(session, "Home University")
    next_university = await seed_university(session, "Next University")
    faculty = await seed_faculty(session, home_university.id, "Proposal Faculty")
    student = await seed_user(session, home_university.id, "proposal-user@example.com")
    headers = access_headers(student)

    university_create = await client.post(
        "/api/v1/catalog-proposals/universities",
        headers=headers,
        json={"name": "Suggested University", "description": "Please add this"},
    )
    faculty_create = await client.post(
        "/api/v1/catalog-proposals/faculties",
        headers=headers,
        json={"university_id": home_university.id, "name": "Suggested Faculty", "description": "Please add"},
    )
    subject_create = await client.post(
        "/api/v1/catalog-proposals/subjects",
        headers=headers,
        json={"faculty_id": faculty.id, "name": "Suggested Subject", "semester": 3},
    )
    assert university_create.status_code == 201
    assert faculty_create.status_code == 201
    assert subject_create.status_code == 201

    university_list = await client.get("/api/v1/users/me/catalog-proposals/universities", headers=headers)
    faculty_list = await client.get("/api/v1/users/me/catalog-proposals/faculties", headers=headers)
    subject_list = await client.get("/api/v1/users/me/catalog-proposals/subjects", headers=headers)
    assert university_list.status_code == 200
    assert faculty_list.status_code == 200
    assert subject_list.status_code == 200
    assert len(university_list.json()) == 1
    assert len(faculty_list.json()) == 1
    assert len(subject_list.json()) == 1

    update_home = await client.patch(
        "/api/v1/users/me/home-university",
        headers=headers,
        json={"university_id": next_university.id},
    )
    assert update_home.status_code == 200
    assert update_home.json()["home_university_id"] == next_university.id

    same_university = await client.patch(
        "/api/v1/users/me/home-university",
        headers=headers,
        json={"university_id": next_university.id},
    )
    assert same_university.status_code == 409

    cooldown_response = await client.patch(
        "/api/v1/users/me/home-university",
        headers=headers,
        json={"university_id": home_university.id},
    )
    assert cooldown_response.status_code == 422
    assert cooldown_response.json()["details"]["error_code"] == "university_change_cooldown"
    assert "next_allowed_at" in cooldown_response.json()["details"]


@pytest.mark.asyncio
async def test_catalog_service_crud_and_conflict_paths(session):
    service = CatalogService(session)

    created_university = await service.create_university(UniversityCreate(name="Service University"))
    other_university = await service.create_university(UniversityCreate(name="Other University"))
    universities = await service.list_universities()
    assert {item.id for item in universities} >= {created_university.id, other_university.id}
    assert (await service.get_university(created_university.id)).name == "Service University"

    with pytest.raises(ConflictError):
        await service.create_university(UniversityCreate(name="service university"))

    created_faculty = await service.create_faculty(
        FacultyCreate(university_id=created_university.id, name="Service Faculty")
    )
    other_faculty = await service.create_faculty(
        FacultyCreate(university_id=other_university.id, name="Other Faculty")
    )
    faculties = await service.list_faculties(created_university.id)
    assert faculties[0].id == created_faculty.id
    assert (await service.get_faculty(created_faculty.id)).name == "Service Faculty"

    with pytest.raises(ConflictError):
        await service.create_faculty(
            FacultyCreate(university_id=created_university.id, name="service faculty")
        )

    created_subject = await service.create_subject(
        SubjectCreate(
            faculty_id=created_faculty.id,
            name="Service Subject",
            code="SVC101",
            description="Initial subject",
        )
    )
    subjects = await service.list_subjects(created_faculty.id)
    assert subjects[0].id == created_subject.id
    assert (await service.get_subject(created_subject.id)).name == "Service Subject"

    with pytest.raises(ConflictError):
        await service.create_subject(
            SubjectCreate(
                faculty_id=created_faculty.id,
                name="service subject",
                code=None,
                description=None,
            )
        )

    updated_university = await service.update_university(
        created_university.id,
        UniversityUpdate(name="Renamed University"),
    )
    assert updated_university.name == "Renamed University"
    assert updated_university.slug == "renamed-university"

    updated_faculty = await service.update_faculty(
        created_faculty.id,
        FacultyUpdate(name="Renamed Faculty", university_id=other_university.id),
    )
    assert updated_faculty.name == "Renamed Faculty"
    assert updated_faculty.university_id == other_university.id

    updated_subject = await service.update_subject(
        created_subject.id,
        SubjectUpdate(
            faculty_id=other_faculty.id,
            name="Renamed Subject",
            code="NEW202",
            description="Updated subject",
        ),
    )
    assert updated_subject.name == "Renamed Subject"
    assert updated_subject.faculty_id == other_faculty.id

    with pytest.raises(ResourceNotFound):
        await service.get_university("missing-id")
    with pytest.raises(ResourceNotFound):
        await service.get_faculty("missing-id")
    with pytest.raises(ResourceNotFound):
        await service.get_subject("missing-id")

    await service.delete_subject(created_subject.id)
    await service.delete_faculty(created_faculty.id)
    await service.delete_university(created_university.id)

    with pytest.raises(ResourceNotFound):
        await service.get_subject(created_subject.id)
    with pytest.raises(ResourceNotFound):
        await service.get_faculty(created_faculty.id)
    with pytest.raises(ResourceNotFound):
        await service.get_university(created_university.id)


@pytest.mark.asyncio
async def test_catalog_proposal_service_validation_paths(session):
    university = await seed_university(session, "Existing University")
    faculty = await seed_faculty(session, university.id, "Existing Faculty")
    await seed_subject(session, faculty.id, "Existing Subject", 1)
    user = await seed_user(session, university.id, "proposal-validation@example.com")
    service = CatalogProposalService(session)

    with pytest.raises(ConflictError):
        await service.create_university_proposal(
            UniversityProposalCreate(name="existing university"),
            user,
        )

    with pytest.raises(ConflictError):
        await service.create_faculty_proposal(
            FacultyProposalCreate(university_id=university.id, name="existing faculty"),
            user,
        )

    with pytest.raises(ConflictError):
        await service.create_subject_proposal(
            SubjectProposalCreate(faculty_id=faculty.id, name="existing subject", semester=1),
            user,
        )

    with pytest.raises(ResourceNotFound):
        await service.update_home_university(user, HomeUniversityUpdateRequest(university_id="missing-id"))

    with pytest.raises(ConflictError):
        await service.update_home_university(user, HomeUniversityUpdateRequest(university_id=university.id))

    first_target = await seed_university(session, "Fresh University")
    await service.update_home_university(user, HomeUniversityUpdateRequest(university_id=first_target.id))
    second_target = await seed_university(session, "Second Fresh University")
    with pytest.raises(ValidationAppError):
        await service.update_home_university(user, HomeUniversityUpdateRequest(university_id=second_target.id))
