import pytest
from fastapi import UploadFile

from app.core.cache import CacheService, RedisError
from app.core.config import get_settings
from app.core.exceptions import ConflictError, ResourceNotFound, ValidationAppError
from app.enums.user_role import UserRole
from app.models.notification import Notification
from app.services.storage_service import StorageService
from tests.helpers import access_headers, png_upload, seed_faculty, seed_material, seed_subject, seed_university, seed_user


@pytest.mark.asyncio
async def test_user_endpoints_cover_profile_preferences_password_and_saved_materials(client, session):
    university = await seed_university(session, "User University")
    faculty = await seed_faculty(session, university.id, "User Faculty")
    subject = await seed_subject(session, faculty.id, "User Subject", 2)
    owner = await seed_user(session, university.id, "owner-user@example.com")
    viewer = await seed_user(session, university.id, "viewer-user@example.com")
    material = await seed_material(session, owner, subject.id, "Owner Material")

    viewer_headers = access_headers(viewer)
    owner_headers = access_headers(owner)

    me_response = await client.get("/api/v1/users/me", headers=viewer_headers)
    assert me_response.status_code == 200
    assert me_response.json()["email"] == viewer.email

    update_me = await client.patch(
        "/api/v1/users/me",
        headers=viewer_headers,
        json={"full_name": "Viewer Updated", "avatar_url": "https://example.com/avatar.png"},
    )
    assert update_me.status_code == 200
    assert update_me.json()["full_name"] == "Viewer Updated"

    preferences_get = await client.get("/api/v1/users/me/preferences", headers=viewer_headers)
    preferences_patch = await client.patch(
        "/api/v1/users/me/preferences",
        headers=viewer_headers,
        json={"language": "uz", "email_notifications": False, "theme": "dark"},
    )
    assert preferences_get.status_code == 200
    assert preferences_patch.status_code == 200
    assert preferences_patch.json()["language"] == "uz"
    assert preferences_patch.json()["email_notifications"] is False
    assert preferences_patch.json()["theme"] == "dark"

    wrong_password = await client.post(
        "/api/v1/users/me/change-password",
        headers=viewer_headers,
        json={"current_password": "wrong-password", "new_password": "new-password123"},
    )
    assert wrong_password.status_code == 409

    change_password = await client.post(
        "/api/v1/users/me/change-password",
        headers=viewer_headers,
        json={"current_password": "password123", "new_password": "new-password123"},
    )
    assert change_password.status_code == 200

    login_new_password = await client.post(
        "/api/v1/auth/login",
        json={"email": viewer.email, "password": "new-password123"},
    )
    assert login_new_password.status_code == 200

    public_user = await client.get(f"/api/v1/users/{owner.id}/public")
    assert public_user.status_code == 200
    assert public_user.json()["id"] == owner.id

    save_material = await client.post(
        f"/api/v1/users/me/saved-materials/{material.id}",
        headers=viewer_headers,
    )
    saved_materials = await client.get("/api/v1/users/me/saved-materials", headers=viewer_headers)
    assert save_material.status_code == 200
    assert saved_materials.status_code == 200
    assert len(saved_materials.json()) == 1
    assert saved_materials.json()[0]["id"] == material.id

    remove_saved = await client.delete(
        f"/api/v1/users/me/saved-materials/{material.id}",
        headers=viewer_headers,
    )
    assert remove_saved.status_code == 200

    await client.post(f"/api/v1/users/me/saved-materials/{material.id}", headers=viewer_headers)
    clear_saved = await client.delete("/api/v1/users/me/saved-materials", headers=viewer_headers)
    assert clear_saved.status_code == 200

    my_materials = await client.get("/api/v1/users/me/materials", headers=owner_headers)
    assert my_materials.status_code == 200
    assert my_materials.json()["total"] == 1
    assert my_materials.json()["items"][0]["id"] == material.id


@pytest.mark.asyncio
async def test_notifications_comments_and_rating_endpoints_cover_community_flows(client, session):
    university = await seed_university(session, "Community University")
    faculty = await seed_faculty(session, university.id, "Community Faculty")
    subject = await seed_subject(session, faculty.id, "Community Subject", 1)
    owner = await seed_user(session, university.id, "community-owner@example.com")
    other_user = await seed_user(session, university.id, "community-other@example.com")
    admin = await seed_user(session, university.id, "community-admin@example.com", role=UserRole.ADMIN)
    material = await seed_material(session, owner, subject.id, "Community Material")

    session.add_all(
        [
            Notification(user_id=owner.id, title="First", body="First notification"),
            Notification(user_id=owner.id, title="Second", body="Second notification"),
        ]
    )
    await session.commit()

    owner_headers = access_headers(owner)
    other_headers = access_headers(other_user)
    admin_headers = access_headers(admin)

    notifications = await client.get("/api/v1/notifications", headers=owner_headers)
    assert notifications.status_code == 200
    assert len(notifications.json()) == 2
    notification_id = notifications.json()[0]["id"]

    read_one = await client.patch(f"/api/v1/notifications/{notification_id}/read", headers=owner_headers)
    read_all = await client.patch("/api/v1/notifications/read-all", headers=owner_headers)
    assert read_one.status_code == 200
    assert read_one.json()["is_read"] is True
    assert read_all.status_code == 200
    assert read_all.json()["updated"] == 2

    list_comments = await client.get(f"/api/v1/materials/{material.id}/comments")
    create_comment = await client.post(
        f"/api/v1/materials/{material.id}/comments",
        headers=owner_headers,
        json={"content": "Initial comment"},
    )
    assert list_comments.status_code == 200
    assert list_comments.json() == []
    assert create_comment.status_code == 200
    comment_id = create_comment.json()["id"]

    update_comment = await client.patch(
        f"/api/v1/comments/{comment_id}",
        headers=owner_headers,
        json={"content": "Updated comment"},
    )
    assert update_comment.status_code == 200
    assert update_comment.json()["content"] == "Updated comment"

    forbidden_delete = await client.delete(f"/api/v1/comments/{comment_id}", headers=other_headers)
    assert forbidden_delete.status_code == 403

    admin_delete = await client.delete(f"/api/v1/comments/{comment_id}", headers=admin_headers)
    assert admin_delete.status_code == 200

    rating_summary = await client.get(f"/api/v1/materials/{material.id}/rating", headers=owner_headers)
    create_rating = await client.post(
        f"/api/v1/materials/{material.id}/rating",
        headers=owner_headers,
        json={"value": 5},
    )
    update_rating = await client.post(
        f"/api/v1/materials/{material.id}/rating",
        headers=owner_headers,
        json={"value": 3},
    )
    delete_rating = await client.delete(f"/api/v1/materials/{material.id}/rating", headers=owner_headers)
    assert rating_summary.status_code == 200
    assert rating_summary.json()["total"] == 0
    assert create_rating.status_code == 200
    assert create_rating.json()["average"] == 5.0
    assert create_rating.json()["my_rating"] == 5
    assert update_rating.status_code == 200
    assert update_rating.json()["average"] == 3.0
    assert delete_rating.status_code == 200


@pytest.mark.asyncio
async def test_storage_service_local_provider_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    storage = StorageService()

    upload = png_upload("sample.png", b"blue")
    stored = await storage.save(upload, "material-1", max_file_size=1024 * 1024)
    assert stored.file_ext == "png"
    assert stored.file_size > 0
    assert await storage.exists(stored.storage_key) is True

    download = await storage.resolve_for_download(stored.storage_key)
    assert download.local_path is not None
    assert download.local_path.exists()

    content = await storage.read_bytes(stored.storage_key)
    assert content.startswith(b"\x89PNG\r\n\x1a\n")

    await storage.save_bytes(b"preview-bytes", "materials/material-1/preview.bin", "application/octet-stream")
    assert await storage.exists("materials/material-1/preview.bin") is True

    await storage.delete(stored.storage_key)
    assert await storage.exists(stored.storage_key) is False

    with pytest.raises(ResourceNotFound):
        await storage.read_bytes("materials/material-1/missing.bin")

    empty_upload = UploadFile(filename="empty.png", file=__import__("io").BytesIO(b""))
    with pytest.raises(ValidationAppError):
        await storage.save(empty_upload, "material-1", max_file_size=1024)

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_cache_service_in_memory_and_redis_fallback(monkeypatch):
    cache = CacheService()
    await cache.initialize(None)
    assert cache.is_redis_enabled is False

    await cache.set("alpha", {"value": 1}, 60)
    await cache.set("alpha:child", {"value": 2}, 60)
    assert await cache.get("alpha") == {"value": 1}
    await cache.invalidate("alpha")
    assert await cache.get("alpha") is None
    await cache.invalidate_prefix("alpha:")
    assert await cache.get("alpha:child") is None

    async def broken_connect(self):
        raise RedisError("broken redis")

    monkeypatch.setattr("app.core.cache.RedisCacheBackend.connect", broken_connect)
    await cache.initialize("redis://127.0.0.1:1/0")
    assert cache.is_redis_enabled is False
    await cache.close()


@pytest.mark.asyncio
async def test_user_service_save_and_unrate_error_paths(session):
    university = await seed_university(session, "Error University")
    faculty = await seed_faculty(session, university.id, "Error Faculty")
    subject = await seed_subject(session, faculty.id, "Error Subject", 1)
    user = await seed_user(session, university.id, "error-user@example.com")
    material = await seed_material(session, user, subject.id, "Error Material")

    from app.services.community_service import CommunityService
    from app.services.user_service import UserService

    with pytest.raises(ResourceNotFound):
        await UserService(session).save_material("missing-material", user)

    with pytest.raises(ConflictError):
        await CommunityService(session).unrate(material.id, user)
