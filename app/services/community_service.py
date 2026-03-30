from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, PermissionDenied, ResourceNotFound
from app.models.comment import Comment
from app.models.material import Material
from app.models.material_rating import MaterialRating
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentUpdate
from app.services.audit_service import AuditService


class CommunityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    async def list_comments(self, material_id: str) -> list[Comment]:
        result = await self.session.execute(
            select(Comment)
            .where(Comment.material_id == material_id)
            .options(selectinload(Comment.user).selectinload(User.university))
            .order_by(Comment.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_comment(self, material_id: str, payload: CommentCreate, user: User) -> Comment:
        material = await self.session.get(Material, material_id)
        if not material:
            raise ResourceNotFound("Material not found")
        comment = Comment(material_id=material_id, user_id=user.id, content=payload.content)
        self.session.add(comment)
        await self.session.flush()
        await self.audit.log("comment_created", "comment", user, comment.id, payload.content[:200])
        await self.session.commit()
        result = await self.session.execute(
            select(Comment)
            .where(Comment.id == comment.id)
            .options(selectinload(Comment.user).selectinload(User.university))
        )
        return result.scalar_one()

    async def update_comment(self, comment_id: str, payload: CommentUpdate, user: User) -> Comment:
        comment = await self.session.get(Comment, comment_id)
        if not comment:
            raise ResourceNotFound("Comment not found")
        if comment.user_id != user.id:
            raise PermissionDenied("You do not own this comment")
        comment.content = payload.content
        await self.audit.log("comment_updated", "comment", user, comment.id, payload.content[:200])
        await self.session.commit()
        result = await self.session.execute(
            select(Comment)
            .where(Comment.id == comment.id)
            .options(selectinload(Comment.user).selectinload(User.university))
        )
        return result.scalar_one()

    async def delete_comment(self, comment_id: str, user: User) -> None:
        comment = await self.session.get(Comment, comment_id)
        if not comment:
            raise ResourceNotFound("Comment not found")
        if comment.user_id != user.id and user.role.value != "admin":
            raise PermissionDenied("You do not own this comment")
        await self.audit.log("comment_deleted", "comment", user, comment.id)
        await self.session.execute(delete(Comment).where(Comment.id == comment_id))
        await self.session.commit()

    async def get_rating_summary(self, material_id: str, user: User | None = None) -> dict:
        material = await self.session.get(Material, material_id)
        if not material:
            raise ResourceNotFound("Material not found")
        result = await self.session.execute(
            select(func.avg(MaterialRating.value), func.count(MaterialRating.id)).where(
                MaterialRating.material_id == material_id
            )
        )
        avg_value, count = result.one()
        my_rating = None
        if user:
            mine = await self.session.execute(
                select(MaterialRating.value).where(
                    MaterialRating.material_id == material_id,
                    MaterialRating.user_id == user.id,
                )
            )
            my_rating = mine.scalar_one_or_none()
        return {
            "average": float(avg_value or 0.0),
            "total": int(count or 0),
            "my_rating": my_rating,
        }

    async def rate(self, material_id: str, value: int, user: User) -> dict:
        material = await self.session.get(Material, material_id)
        if not material:
            raise ResourceNotFound("Material not found")
        existing = await self.session.execute(
            select(MaterialRating).where(
                MaterialRating.material_id == material_id,
                MaterialRating.user_id == user.id,
            )
        )
        rating = existing.scalar_one_or_none()
        if rating:
            rating.value = value
            action = "rating_updated"
        else:
            rating = MaterialRating(material_id=material_id, user_id=user.id, value=value)
            self.session.add(rating)
            action = "rating_created"
        await self.audit.log(action, "material_rating", user, material_id, str(value))
        await self.session.commit()
        return await self.get_rating_summary(material_id, user)

    async def unrate(self, material_id: str, user: User) -> None:
        existing = await self.session.execute(
            select(MaterialRating).where(
                MaterialRating.material_id == material_id,
                MaterialRating.user_id == user.id,
            )
        )
        rating = existing.scalar_one_or_none()
        if not rating:
            raise ConflictError("Rating does not exist")
        await self.audit.log("rating_deleted", "material_rating", user, material_id)
        await self.session.execute(delete(MaterialRating).where(MaterialRating.id == rating.id))
        await self.session.commit()
