"""User and Plan models."""
import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, Enum, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class UserRole(str, enum.Enum):
    """User role enumeration."""
    ADMIN = "admin"
    USER = "user"


class PlanType(str, enum.Enum):
    """Plan type enumeration."""
    FREE = "free"
    LITE = "lite"
    PRO = "pro"
    CORPORATE = "corporate"


class User(Base):
    """User model with authentication and plan information."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Plan and quota
    plan_type: Mapped[PlanType] = mapped_column(
        Enum(PlanType),
        default=PlanType.FREE,
        nullable=False,
        index=True,
    )
    plan_expires_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        default=None,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole),
        default=UserRole.USER,
        nullable=False,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    scans = relationship(
        "Scan",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    usage_trackers = relationship(
        "UsageTracker",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return self.role == UserRole.ADMIN

    @property
    def is_premium(self) -> bool:
        """Check if user has paid plan."""
        return self.plan_type in (PlanType.LITE, PlanType.PRO, PlanType.CORPORATE)


class Plan(Base):
    """Plan configuration with quotas and pricing."""

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    slug: Mapped[PlanType] = mapped_column(
        Enum(PlanType),
        unique=True,
        nullable=False,
    )

    # Quotas
    max_urls_per_scan: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_domains_per_week: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
    )

    # Pricing (in IDR)
    price_monthly: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    # Features
    features: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
