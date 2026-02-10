"""User schemas for request/response validation."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import PlanType, UserRole


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: int | None = None  # user_id
    exp: int | None = None
    type: Literal["access"] = "access"


class UserBase(BaseModel):
    """Base user fields."""
    email: EmailStr
    full_name: str | None = None


class RegisterRequest(UserBase):
    """Registration request."""
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        """Validate that passwords match."""
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    """Login request."""
    email: EmailStr
    password: str


class UserResponse(UserBase):
    """User response."""
    id: int
    role: UserRole
    plan_type: PlanType
    plan_expires_at: datetime | None
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """User update request."""
    full_name: str | None = None


class PlanResponse(BaseModel):
    """Plan response."""
    id: int
    name: str
    slug: PlanType
    max_urls_per_scan: int
    max_domains_per_week: int
    price_monthly: int | None
    features: str | None
    is_active: bool
    display_order: int

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    """Login response with token."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
