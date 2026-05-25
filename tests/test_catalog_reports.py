import pytest
from app.modules.users.enums import UserRole
from app.modules.materials.enums import ReportStatus
from tests.helpers import access_headers, seed_user, seed_university, seed_faculty, seed_subject


@pytest.mark.asyncio
async def test_catalog_report_lifecycle(client, session):
    # 1. Seed test data
    university = await seed_university(session, "Report University")
    faculty = await seed_faculty(session, university.id, "Report Faculty")
    subject = await seed_subject(session, faculty.id, "Report Subject", 2)

    student = await seed_user(session, university.id, "reporter@example.com")
    admin = await seed_user(session, university.id, "report-admin@example.com")
    
    # Set roles
    admin.role = UserRole.ADMIN
    await session.commit()

    student_headers = access_headers(student)
    admin_headers = access_headers(admin)

    # 2. Test user submission
    # Submit report for University
    uni_report_res = await client.post(
        "/api/v1/catalog-proposals/reports",
        headers=student_headers,
        json={
            "entity_type": "university",
            "entity_id": university.id,
            "reason": "incorrect_name",
            "details": "The name is misspelled"
        }
    )
    assert uni_report_res.status_code == 201
    uni_report_data = uni_report_res.json()
    assert "id" in uni_report_data
    assert uni_report_data["status"] == "open"
    assert uni_report_data["message"] == "Shikoyat muvaffaqiyatli qabul qilindi"

    # Submit report for Faculty
    fac_report_res = await client.post(
        "/api/v1/catalog-proposals/reports",
        headers=student_headers,
        json={
            "entity_type": "faculty",
            "entity_id": faculty.id,
            "reason": "duplicate",
            "details": "This faculty is duplicated"
        }
    )
    assert fac_report_res.status_code == 201

    # Submit report for Subject
    sub_report_res = await client.post(
        "/api/v1/catalog-proposals/reports",
        headers=student_headers,
        json={
            "entity_type": "subject",
            "entity_id": subject.id,
            "reason": "does_not_exist",
            "details": "No longer offered"
        }
    )
    assert sub_report_res.status_code == 201

    # Test invalid entity type pattern validation
    invalid_type_res = await client.post(
        "/api/v1/catalog-proposals/reports",
        headers=student_headers,
        json={
            "entity_type": "material",  # Not allowed by pattern
            "entity_id": university.id,
            "reason": "wrong",
        }
    )
    assert invalid_type_res.status_code == 422

    # Test non-existent entity ID
    non_existent_res = await client.post(
        "/api/v1/catalog-proposals/reports",
        headers=student_headers,
        json={
            "entity_type": "university",
            "entity_id": "00000000-0000-0000-0000-000000000000",
            "reason": "wrong_name",
        }
    )
    assert non_existent_res.status_code == 404

    # 3. Test list reports endpoint
    # Test permission check (student cannot access admin list)
    student_list_res = await client.get("/api/v1/admin/catalog-reports", headers=student_headers)
    assert student_list_res.status_code == 403

    # Admin list reports
    admin_list_res = await client.get("/api/v1/admin/catalog-reports", headers=admin_headers)
    assert admin_list_res.status_code == 200
    list_data = admin_list_res.json()
    assert list_data["total"] == 3
    assert len(list_data["items"]) == 3

    # Admin list with status filter
    admin_list_open_res = await client.get("/api/v1/admin/catalog-reports?status=open", headers=admin_headers)
    assert admin_list_open_res.status_code == 200
    assert admin_list_open_res.json()["total"] == 3

    # Admin list with entity_type filter
    admin_list_uni_res = await client.get("/api/v1/admin/catalog-reports?entity_type=university", headers=admin_headers)
    assert admin_list_uni_res.status_code == 200
    assert admin_list_uni_res.json()["total"] == 1

    # 4. Test detail view endpoint
    report_id = uni_report_data["id"]
    detail_res = await client.get(f"/api/v1/admin/catalog-reports/{report_id}", headers=admin_headers)
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["entity_name"] == "Report University"
    assert detail_data["reason"] == "incorrect_name"
    assert detail_data["details"] == "The name is misspelled"
    assert detail_data["reporter"]["full_name"] == student.full_name

    # Test invalid report ID
    invalid_report_res = await client.get("/api/v1/admin/catalog-reports/00000000-0000-0000-0000-000000000000", headers=admin_headers)
    assert invalid_report_res.status_code == 404

    # 5. Test resolution endpoints
    # Resolve university report
    resolve_res = await client.post(
        f"/api/v1/admin/catalog-reports/{report_id}/resolve",
        headers=admin_headers,
        json={"resolution_note": "Misspelling fixed"}
    )
    assert resolve_res.status_code == 200
    resolve_data = resolve_res.json()
    assert resolve_data["status"] == "resolved"
    assert resolve_data["resolution_note"] == "Misspelling fixed"
    assert resolve_data["reviewer"]["full_name"] == admin.full_name

    # Dismiss faculty report
    fac_report_id = fac_report_res.json()["id"]
    dismiss_res = await client.post(
        f"/api/v1/admin/catalog-reports/{fac_report_id}/dismiss",
        headers=admin_headers,
        json={"resolution_note": "Not a duplicate"}
    )
    assert dismiss_res.status_code == 200
    dismiss_data = dismiss_res.json()
    assert dismiss_data["status"] == "dismissed"
    assert dismiss_data["resolution_note"] == "Not a duplicate"
