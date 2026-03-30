from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.user_role import UserRole
from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id).options(selectinload(User.university))
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email).options(selectinload(User.university))
        )
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def list_filtered(
        self,
        q: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        university_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ):
        statement = select(User).options(selectinload(User.university))
        if q:
            statement = statement.where(
                func.lower(User.full_name).contains(q.lower()) | func.lower(User.email).contains(q.lower())
            )
        if role:
            statement = statement.where(User.role == UserRole(role))
        if is_active is not None:
            statement = statement.where(User.is_active == is_active)
        if university_id:
            statement = statement.where(User.university_id == university_id)
        count_stmt = select(func.count()).select_from(statement.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()
        result = await self.session.execute(
            statement.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), total
