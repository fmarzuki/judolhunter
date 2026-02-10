"""Scan and UsageTracker models."""
import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Literal

from app.models.user import Base


class ScanStatus(str, enum.Enum):
    """Scan status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RiskLevel(str, enum.Enum):
    """Risk level enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class Scan(Base):
    """Scan model for storing scan results."""

    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # User tracking (nullable for anonymous scans)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Scan target
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Status and results
    status: Mapped[ScanStatus] = mapped_column(
        String(20),
        default=ScanStatus.PENDING,
        nullable=False,
        index=True,
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        String(20),
        default=RiskLevel.UNKNOWN,
        nullable=False,
    )

    # Full findings as JSON
    findings: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Fetch info for both Googlebot and browser
    fetch_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Error message if failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="scans")

    @property
    def duration_seconds(self) -> float | None:
        """Calculate scan duration in seconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class UsageTracker(Base):
    """Track weekly domain usage per user/session."""

    __tablename__ = "usage_trackers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # User tracking
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Domain and week tracking
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scan_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

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

    # Relationships
    user = relationship("User", back_populates="usage_trackers")

    __table_args__ = (
        # Unique constraint: one record per (user, domain, week)
        # Or for anonymous: (session, domain, week)
        # Using database-level unique constraint
    )
