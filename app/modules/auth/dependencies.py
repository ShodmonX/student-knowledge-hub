from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, PermissionDenied
from app.core.security import decode_token
from app.db.session import get_db_session
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.modules.users.repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise AuthenticationError("Invalid access token")
    user = await UserRepository(session).get_by_id(payload["sub"])
    if not user:
        raise AuthenticationError("User not found")
    return user


async def get_optional_user(
    token: Annotated[str | None, Depends(optional_oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User | None:
    if not token:
        return None
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise AuthenticationError("Invalid access token")
    return await UserRepository(session).get_by_id(payload["sub"])


def require_roles(*roles: UserRole):
    async def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise PermissionDenied("Insufficient permissions")
        return user

    return dependency
