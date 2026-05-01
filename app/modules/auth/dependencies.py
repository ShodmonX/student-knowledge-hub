import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, PermissionDenied
from app.core.security import decode_token
from app.core.security_controls import AccessTokenRevocationStore
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
    await AccessTokenRevocationStore().ensure_not_revoked(payload)
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
    await AccessTokenRevocationStore().ensure_not_revoked(payload)
    return await UserRepository(session).get_by_id(payload["sub"])


def require_roles(*roles: UserRole):
    async def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise PermissionDenied("Insufficient permissions")
        return user

    return dependency


async def require_internal_service(
    request: Request,
    x_internal_service_name: Annotated[str | None, Header(alias="X-Internal-Service-Name")] = None,
    x_request_timestamp: Annotated[str | None, Header(alias="X-Request-Timestamp")] = None,
    x_signature: Annotated[str | None, Header(alias="X-Signature")] = None,
) -> str:
    settings = get_settings()
    if not settings.internal_service_secret:
        raise AuthenticationError("Internal service auth is not configured")
    if not x_internal_service_name or not x_request_timestamp or not x_signature:
        raise AuthenticationError("Invalid internal service signature")
    if not secrets.compare_digest(x_internal_service_name, settings.internal_service_name):
        raise AuthenticationError("Invalid internal service signature")

    try:
        request_dt = datetime.fromtimestamp(int(x_request_timestamp), tz=UTC)
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("Invalid internal service signature") from exc

    now = datetime.now(UTC)
    age_seconds = abs((now - request_dt).total_seconds())
    if age_seconds > settings.internal_request_ttl_seconds:
        raise AuthenticationError("Internal request signature expired")

    body = await request.body()
    canonical_path = request.url.path
    if request.url.query:
        canonical_path = f"{canonical_path}?{request.url.query}"
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(
        [
            x_internal_service_name,
            x_request_timestamp,
            request.method.upper(),
            canonical_path,
            payload_hash,
        ]
    )
    expected_signature = hmac.new(
        settings.internal_service_secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not secrets.compare_digest(x_signature, expected_signature):
        raise AuthenticationError("Invalid internal service signature")
    return x_internal_service_name
