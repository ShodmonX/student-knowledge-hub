from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, ResourceNotFound
from app.core.security import hash_password, verify_password
from app.modules.catalog.models import Faculty, Subject
from app.modules.materials.models import Material, MaterialDownload
from app.modules.auth.models import RefreshTokenSession
from app.modules.auth.schemas import ChangePasswordRequest
from app.modules.notifications.models import Notification
from app.modules.notifications.service import NotificationService
from app.modules.users.models import SavedMaterial, User, UserPreference
from app.modules.users.schemas import UserPreferenceUpdate, UserUpdateMe
from app.modules.users.repository import UserRepository
from app.modules.materials.repositories import MaterialRepository
from app.modules.materials.schemas import MaterialListQuery
from app.modules.audit.service import AuditService


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
        return await NotificationService(self.session).list_notifications(user)

    async def mark_notification_read(self, notification_id: str, user: User) -> Notification:
        return await NotificationService(self.session).mark_notification_read(notification_id, user)

    async def mark_all_notifications_read(self, user: User) -> int:
        return await NotificationService(self.session).mark_all_notifications_read(user)

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

    async def list_downloaded_materials(self, user: User) -> list[Material]:
        result = await self.session.execute(
            select(Material)
            .join(MaterialDownload, MaterialDownload.material_id == Material.id)
            .where(MaterialDownload.user_id == user.id, Material.deleted_at.is_(None))
            .options(
                selectinload(Material.files),
                selectinload(Material.tags),
                selectinload(Material.subject).selectinload(Subject.faculty).selectinload(Faculty.university),
                selectinload(Material.uploader).selectinload(User.university),
            )
            .order_by(MaterialDownload.created_at.desc())
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
