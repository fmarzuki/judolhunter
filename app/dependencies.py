"""Dependency injection for FastAPI routes."""
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import decode_token
from app.models.user import User
from app.schemas.user import TokenPayload
from app.utils.db import get_async_session

settings = get_settings()
security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session."""
    async for session in get_async_session():
        yield session


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Get current authenticated user from JWT token.

    Returns None if no valid token is provided (for optional auth).
    Only raises HTTPException if token is provided but invalid.
    """
    if credentials is None:
        return None

    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        # Token provided but invalid - return None to allow anonymous access
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return None

    from sqlalchemy import select

    result = await session.execute(
        select(User).where(User.id == user_id),
    )
    user = result.scalar_one_or_none()

    if user is None:
        return None

    if not user.is_active:
        return None

    return user


async def require_auth(
    user: Annotated[User | None, Depends(get_current_user)],
) -> User:
    """Require authentication - raises 401 if not authenticated."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(
    user: Annotated[User, Depends(require_auth)],
) -> User:
    """Require admin role - raises 403 if not admin."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


# Type aliases for cleaner injection
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User | None, Depends(get_current_user)]
AuthUser = Annotated[User, Depends(require_auth)]
AdminUser = Annotated[User, Depends(require_admin)]
