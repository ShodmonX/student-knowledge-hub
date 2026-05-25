from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.exceptions import ResourceNotFound
from app.modules.auth.models import EmailOutbox, PasswordResetToken, RefreshTokenSession
from app.modules.auth.schemas import RegisterRequest
from app.modules.auth.service import AuthService
from app.modules.materials.enums import MaterialStatus, MaterialType
from app.modules.materials.models import Material
from app.modules.materials.service import MaterialService
from app.utils.hashing import sha256_text
from tests.helpers import (
    access_headers,
    seed_faculty,
    seed_material,
    seed_subject,
    seed_university,
    seed_user,
)


def _extract_token_from_email(message: EmailOutbox) -> str:
    for word in message.text_body.split():
        if "token=" in word:
            return parse_qs(urlparse(word).query)["token"][0]
    raise AssertionError("email token link not found")


@pytest.mark.asyncio
async def test_auth_flows_cover_reset_logout_and_revocation_paths(client, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "mail_enabled", True)
    university = await seed_university(session, "Auth University")

    register = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Auth User",
            "email": "auth-user@example.com",
            "password": "password123",
            "university_id": university.id,
        },
    )
    assert register.status_code == 201

    duplicate_register = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Auth User",
            "email": "auth-user@example.com",
            "password": "password123",
            "university_id": university.id,
        },
    )
    assert duplicate_register.status_code == 409

    wrong_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "auth-user@example.com", "password": "wrong-password"},
    )
    assert wrong_login.status_code == 401

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "auth-user@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    access_token = login.json()["access_token"]

    invalid_refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert invalid_refresh.status_code == 401

    logout_without_payload = await client.post("/api/v1/auth/logout")
    assert logout_without_payload.status_code == 200

    logout_invalid_token_type = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": access_token},
    )
    assert logout_invalid_token_type.status_code == 401

    forgot_password = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "auth-user@example.com"},
    )
    assert forgot_password.status_code == 200

    reset_token = await session.scalar(
        select(PasswordResetToken).order_by(PasswordResetToken.created_at.desc())
    )
    assert reset_token is not None
    reset_email = await session.scalar(
        select(EmailOutbox)
        .where(EmailOutbox.recipient_email == "auth-user@example.com")
        .order_by(EmailOutbox.created_at.desc())
    )
    assert reset_email is not None
    raw_reset_token = _extract_token_from_email(reset_email)
    assert reset_token.token == sha256_text(raw_reset_token)

    invalid_reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "missing-token", "new_password": "brand-new-password123"},
    )
    assert invalid_reset.status_code == 401

    reset_password = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_reset_token, "new_password": "brand-new-password123"},
    )
    assert reset_password.status_code == 200

    reused_reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_reset_token, "new_password": "another-password123"},
    )
    assert reused_reset.status_code == 401

    login_with_old_password = await client.post(
        "/api/v1/auth/login",
        json={"email": "auth-user@example.com", "password": "password123"},
    )
    login_with_new_password = await client.post(
        "/api/v1/auth/login",
        json={"email": "auth-user@example.com", "password": "brand-new-password123"},
    )
    assert login_with_old_password.status_code == 401
    assert login_with_new_password.status_code == 200

    user = await AuthService(session).users.get_by_email("auth-user@example.com")
    assert user is not None
    await AuthService(session).revoke_user_sessions(user.id)
    await session.commit()
    active_sessions = (
        await session.execute(
            select(RefreshTokenSession).where(
                RefreshTokenSession.user_id == user.id,
                RefreshTokenSession.revoked_at.is_(None),
            )
        )
    ).scalars().all()
    assert active_sessions == []

    with pytest.raises(ResourceNotFound):
        await AuthService(session).register(
            RegisterRequest(
                full_name="Missing University User",
                email="missing-university@example.com",
                password="password123",
                university_id="missing-university-id",
            )
        )


@pytest.mark.asyncio
async def test_material_routes_cover_lifecycle_public_access_and_discovery(client, session, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()

    university = await seed_university(session, "Material University")
    faculty = await seed_faculty(session, university.id, "Material Faculty")
    subject = await seed_subject(session, faculty.id, "Material Subject", 2)
    owner = await seed_user(session, university.id, "material-owner@example.com")
    viewer = await seed_user(session, university.id, "material-viewer@example.com")
    owner_headers = access_headers(owner)
    viewer_headers = access_headers(viewer)

    create_material = await client.post(
        "/api/v1/materials",
        headers=owner_headers,
        json={
            "title": "API Material",
            "description": "Lifecycle material",
            "material_type": MaterialType.NOTES.value,
            "subject_id": subject.id,
            "semesters": [2],
        },
    )
    assert create_material.status_code == 200
    material_id = create_material.json()["id"]
    material_slug = create_material.json()["slug"]

    formats_response = await client.get("/api/v1/materials/formats")
    assert formats_response.status_code == 200
    assert "png" in formats_response.json()["accepted_extensions"]

    upload_bytes = b"\x89PNG\r\n\x1a\nmaterial-upload"
    attach_files = await client.post(
        f"/api/v1/materials/{material_id}/files",
        headers=owner_headers,
        data={"file_orders": "0"},
        files={"files": ("cover.png", upload_bytes, "image/png")},
    )
    assert attach_files.status_code == 200
    file_id = attach_files.json()[0]["id"]

    reorder_files = await client.patch(
        f"/api/v1/materials/{material_id}/files/reorder",
        headers=owner_headers,
        json={"file_ids": [file_id]},
    )
    assert reorder_files.status_code == 200

    select_file = await client.patch(
        f"/api/v1/materials/{material_id}/files/{file_id}",
        headers=owner_headers,
        json={"cover": True, "primary": True},
    )
    assert select_file.status_code == 200
    assert select_file.json()["cover_file_id"] == file_id
    assert select_file.json()["primary_file_id"] == file_id

    resources_response = await client.get(f"/api/v1/materials/{material_id}/resources")
    assert resources_response.status_code == 200
    assert resources_response.json()[0]["id"] == file_id

    submit_once = await client.post(f"/api/v1/materials/{material_id}/submit", headers=owner_headers)
    assert submit_once.status_code == 200
    assert submit_once.json()["status"] == "pending_review"

    withdraw = await client.post(f"/api/v1/materials/{material_id}/withdraw", headers=owner_headers)
    assert withdraw.status_code == 200
    assert withdraw.json()["status"] == "draft"

    update_material = await client.patch(
        f"/api/v1/materials/{material_id}",
        headers=owner_headers,
        json={"title": "API Material Updated"},
    )
    assert update_material.status_code == 200
    material_slug = update_material.json()["slug"]

    submit_again = await client.post(f"/api/v1/materials/{material_id}/submit", headers=owner_headers)
    assert submit_again.status_code == 200
    secondary_material = await seed_material(
        session,
        owner,
        subject.id,
        "Related Material",
        status=MaterialStatus.APPROVED,
    )
    primary_material = await session.get(Material, material_id)
    assert primary_material is not None
    primary_material.status = MaterialStatus.APPROVED
    primary_material.reviewed_at = datetime.now(UTC)
    secondary_material.reviewed_at = datetime.now(UTC) - timedelta(hours=1)
    secondary_material.download_count = 9
    session.add(primary_material)
    session.add(secondary_material)
    await session.commit()

    detail_by_id = await client.get(f"/api/v1/materials/{material_id}")
    detail_by_slug = await client.get(f"/api/v1/materials/slug/{material_slug}")
    list_materials = await client.get("/api/v1/materials", params={"q": "API Material"})
    search_materials = await client.get("/api/v1/materials/search", params={"q": "API Material"})
    featured = await client.get("/api/v1/materials/featured")
    trending = await client.get("/api/v1/materials/trending")
    stats_summary = await client.get("/api/v1/materials/stats/summary")
    related = await client.get(f"/api/v1/materials/{material_id}/related")
    sitemap = await client.get("/api/v1/materials/sitemap.xml")
    assert detail_by_id.status_code == 200
    assert detail_by_id.json()["id"] == material_id
    assert detail_by_id.json()["access_level"] == "public"
    assert detail_by_id.json()["can_download"] is False
    assert detail_by_slug.status_code == 200
    assert detail_by_slug.json()["id"] == material_id
    assert list_materials.status_code == 200
    assert list_materials.json()["total"] >= 1
    assert search_materials.status_code == 200
    assert search_materials.json()["total"] >= 1
    assert featured.status_code == 200
    assert any(item["id"] == material_id for item in featured.json())
    assert trending.status_code == 200
    assert any(item["id"] == secondary_material.id for item in trending.json())
    assert stats_summary.status_code == 200
    assert stats_summary.json()["approved_materials"] >= 2
    assert related.status_code == 200
    assert any(item["id"] == secondary_material.id for item in related.json())
    assert sitemap.status_code == 200
    assert material_slug in sitemap.text

    preview_by_id = await client.get(f"/api/v1/materials/{material_id}/files/{file_id}/preview")
    preview_by_slug = await client.get(f"/api/v1/materials/slug/{material_slug}/files/{file_id}/preview")
    assert preview_by_id.status_code == 200
    assert "preview_url" in preview_by_id.json()
    assert preview_by_slug.status_code == 200
    assert "preview_url" in preview_by_slug.json()

    # Now verify the URL actually works
    preview_url = preview_by_id.json()["preview_url"]
    file_request = await client.get(preview_url)
    assert file_request.status_code == 200
    assert file_request.content.startswith(b"\x89PNG\r\n\x1a\n")

    unauth_download = await client.get(f"/api/v1/materials/{material_id}/download")
    unauth_file_download = await client.get(f"/api/v1/materials/{material_id}/files/{file_id}/download")
    assert unauth_download.status_code == 401
    assert unauth_file_download.status_code == 401

    auth_download = await client.get(f"/api/v1/materials/{material_id}/download", headers=viewer_headers)
    auth_download_by_slug = await client.get(
        f"/api/v1/materials/slug/{material_slug}/download",
        headers=viewer_headers,
    )
    auth_file_download = await client.get(
        f"/api/v1/materials/{material_id}/files/{file_id}/download",
        headers=viewer_headers,
    )
    auth_file_download_by_slug = await client.get(
        f"/api/v1/materials/slug/{material_slug}/files/{file_id}/download",
        headers=viewer_headers,
    )
    assert auth_download.status_code == 200
    assert auth_download.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert auth_download_by_slug.status_code == 200
    assert auth_download_by_slug.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert auth_file_download.status_code == 200
    assert auth_file_download.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert auth_file_download_by_slug.status_code == 200
    assert auth_file_download_by_slug.content.startswith(b"\x89PNG\r\n\x1a\n")

    report_material = await client.post(
        f"/api/v1/materials/{material_id}/report",
        headers=viewer_headers,
        json={"reason": "spam", "details": "Needs moderation review"},
    )
    assert report_material.status_code == 200

    delete_material = await client.delete(f"/api/v1/materials/{material_id}", headers=owner_headers)
    deleted_detail = await client.get(f"/api/v1/materials/{material_id}", headers=owner_headers)
    assert delete_material.status_code == 200
    assert deleted_detail.status_code == 404

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_material_service_cleanup_stale_drafts(session, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()

    university = await seed_university(session, "Cleanup University")
    faculty = await seed_faculty(session, university.id, "Cleanup Faculty")
    subject = await seed_subject(session, faculty.id, "Cleanup Subject", 1)
    user = await seed_user(session, university.id, "cleanup-user@example.com")
    stale_draft = await seed_material(session, user, subject.id, "Stale Draft")
    fresh_draft = await seed_material(session, user, subject.id, "Fresh Draft")

    stale_draft.updated_at = datetime.now(UTC) - timedelta(days=8)
    fresh_draft.updated_at = datetime.now(UTC)
    session.add(stale_draft)
    session.add(fresh_draft)
    await session.commit()

    deleted_count = await MaterialService(session).cleanup_stale_drafts()
    assert deleted_count == 1

    refreshed_stale = await session.get(Material, stale_draft.id)
    refreshed_fresh = await session.get(Material, fresh_draft.id)
    assert refreshed_stale is not None and refreshed_stale.deleted_at is not None
    assert refreshed_fresh is not None and refreshed_fresh.deleted_at is None

    get_settings.cache_clear()
