from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, ResourceNotFound
from app.core.security import hash_password, verify_password
from app.models.material import Material
from app.models.notification import Notification
from app.models.refresh_token_session import RefreshTokenSession
from app.models.saved_material import SavedMaterial
from app.models.faculty import Faculty
from app.models.subject import Subject
from app.models.user import User
from app.models.user_preference import UserPreference
from app.repositories.material_repository import MaterialRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import ChangePasswordRequest
from app.schemas.material import MaterialListQuery
from app.schemas.preferences import UserPreferenceUpdate
from app.schemas.user import UserUpdateMe
from app.services.audit_service import AuditService


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.materials = MaterialRepository(session)
        self.audit = AuditService(session)

    async def get_user(self, user_id: str) -> User:
        user = await self.users.get_by_id(user_id)
        if not user:
            raise ResourceNotFound("User not found")
        return user

    async def update_me(self, user: User, payload: UserUpdateMe) -> User:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        await self.audit.log("user_profile_updated", "user", user, user.id)
        await self.session.commit()
        return await self.get_user(user.id)

    async def change_password(self, user: User, payload: ChangePasswordRequest) -> None:
        if not verify_password(payload.current_password, user.hashed_password):
            raise ConflictError("Current password is incorrect")
        user.hashed_password = hash_password(payload.new_password)
        await self.session.execute(
            update(RefreshTokenSession)
            .where(
                RefreshTokenSession.user_id == user.id,
                RefreshTokenSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await self.audit.log("user_password_changed", "user", user, user.id)
        await self.session.commit()

    async def get_preferences(self, user: User) -> UserPreference:
        pref = await self.session.execute(select(UserPreference).where(UserPreference.user_id == user.id))
        preference = pref.scalar_one_or_none()
        if preference:
            return preference
        preference = UserPreference(user_id=user.id)
        self.session.add(preference)
        await self.session.commit()
        return preference

    async def update_preferences(self, user: User, payload: UserPreferenceUpdate) -> UserPreference:
        preference = await self.get_preferences(user)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(preference, field, value)
        await self.audit.log("user_preferences_updated", "user_preference", user, preference.id)
        await self.session.commit()
        return preference

    async def list_notifications(self, user: User) -> list[Notification]:
        result = await self.session.execute(
            select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc())
        )
        return list(result.scalars().all())

    async def mark_notification_read(self, notification_id: str, user: User) -> Notification:
        notification = await self.session.get(Notification, notification_id)
        if not notification or notification.user_id != user.id:
            raise ResourceNotFound("Notification not found")
        notification.is_read = True
        await self.session.commit()
        return notification

    async def mark_all_notifications_read(self, user: User) -> int:
        notifications = await self.list_notifications(user)
        for item in notifications:
            item.is_read = True
        await self.session.commit()
        return len(notifications)

    async def list_saved_materials(self, user: User) -> list[Material]:
        result = await self.session.execute(
            select(Material)
            .join(SavedMaterial, SavedMaterial.material_id == Material.id)
            .where(SavedMaterial.user_id == user.id, Material.deleted_at.is_(None))
            .options(
                selectinload(Material.files),
                selectinload(Material.tags),
                selectinload(Material.subject).selectinload(Subject.faculty).selectinload(Faculty.university),
                selectinload(Material.uploader).selectinload(User.university),
            )
            .order_by(SavedMaterial.created_at.desc())
        )
        return list(result.scalars().all())

    async def save_material(self, material_id: str, user: User) -> None:
        material = await self.materials.get(material_id)
        if not material:
            raise ResourceNotFound("Material not found")
        existing = await self.session.execute(
            select(SavedMaterial).where(SavedMaterial.user_id == user.id, SavedMaterial.material_id == material_id)
        )
        if existing.scalar_one_or_none():
            return
        self.session.add(SavedMaterial(user_id=user.id, material_id=material_id))
        await self.audit.log("saved_material_added", "saved_material", user, material_id)
        await self.session.commit()

    async def remove_saved_material(self, material_id: str, user: User) -> None:
        await self.session.execute(
            delete(SavedMaterial).where(SavedMaterial.user_id == user.id, SavedMaterial.material_id == material_id)
        )
        await self.audit.log("saved_material_removed", "saved_material", user, material_id)
        await self.session.commit()

    async def clear_saved_materials(self, user: User) -> None:
        await self.session.execute(delete(SavedMaterial).where(SavedMaterial.user_id == user.id))
        await self.audit.log("saved_materials_cleared", "saved_material", user, user.id)
        await self.session.commit()

    async def list_user_materials(self, user: User, query: MaterialListQuery):
        statement = self.materials.build_filtered_query().where(Material.uploaded_by == user.id)
        statement = self.materials.apply_filters(statement, query)
        return await self.materials.list_filtered(statement, query.page, query.page_size)
