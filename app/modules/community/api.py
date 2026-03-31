from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.community.schemas import CommentRead, CommentUpdate
from app.modules.community.service import CommunityService
from app.modules.users.models import User
from app.utils.serializers import build_comment_read

router = APIRouter()


@router.patch("/{comment_id}", response_model=CommentRead)
async def update_comment(
    comment_id: str,
    payload: CommentUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CommentRead:
    comment = await CommunityService(session).update_comment(comment_id, payload, user)
    return build_comment_read(comment)


@router.delete("/{comment_id}")
async def delete_comment(
    comment_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await CommunityService(session).delete_comment(comment_id, user)
    return {"message": "Comment deleted"}
