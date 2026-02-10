"""Authentication API endpoints."""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash, verify_password
from app.dependencies import AuthUser, CurrentUser, DbSession
from app.models.user import PlanType, User
from app.schemas.user import (
    LoginRequest,
    LoginResponse,
    PlanResponse,
    RegisterRequest,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
security = HTTPBearer()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    session: DbSession,
):
    """Register a new user account."""
    # Check if email already exists
    result = await session.execute(
        select(User).where(User.email == data.email),
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name,
        plan_type=PlanType.FREE,
        is_active=True,
        is_verified=False,  # Could implement email verification
        role="user",
    )

    session.add(user)
    await session.commit()
    await session.refresh(user)

    return user


@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    session: DbSession,
):
    """Authenticate user and return access token."""
    # Find user by email
    result = await session.execute(
        select(User).where(User.email == data.email),
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    # Update last login
    user.last_login_at = datetime.utcnow()
    await session.commit()

    # Create access token
    access_token = create_access_token(subject=user.id)

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=user,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: CurrentUser,
):
    """Get current authenticated user profile."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    session: DbSession,
    user: AuthUser,
):
    """Update current user profile."""
    if data.full_name is not None:
        user.full_name = data.full_name

    await session.commit()
    await session.refresh(user)

    return user


@router.post("/logout")
async def logout():
    """Logout user (client-side token deletion).

    Note: Since we use JWT tokens without server-side storage,
    the actual logout is handled by the client deleting the token.
    This endpoint exists for future token blacklisting if needed.
    """
    return {"message": "Successfully logged out"}


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    session: DbSession,
    user: CurrentUser = None,
):
    """List available subscription plans."""
    from app.models.user import Plan

    result = await session.execute(
        select(Plan)
        .where(Plan.is_active == True)
        .order_by(Plan.display_order, Plan.price_monthly),
    )
    plans = result.scalars().all()

    return plans


# Import HTTPException at module level
from fastapi import HTTPException
