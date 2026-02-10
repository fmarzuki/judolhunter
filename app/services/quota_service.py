"""Quota validation and management service."""
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiter import check_quota, record_usage
from app.models.scan import Scan, ScanStatus
from app.models.user import User


class QuotaService:
    """Service for managing scan quotas."""

    @staticmethod
    async def validate_scan_request(
        session: AsyncSession,
        user: User | None,
        session_id: str | None,
        urls: list[str],
    ) -> tuple[bool, str | None]:
        """Validate if user/session has quota for the requested scan.

        Returns:
            (allowed, error_message)
        """
        return await check_quota(session, user, session_id, urls)

    @staticmethod
    async def create_scan_job(
        session: AsyncSession,
        user: User | None,
        session_id: str | None,
        url: str,
    ) -> Scan:
        """Create a new scan job in the database."""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove www. prefix for consistency
        if domain.startswith("www."):
            domain = domain[4:]

        scan = Scan(
            user_id=user.id if user else None,
            session_id=session_id if not user else None,
            url=url,
            domain=domain,
            status=ScanStatus.PENDING,
            risk_level="unknown",
        )

        session.add(scan)
        await session.flush()

        return scan

    @staticmethod
    async def record_domain_usage(
        session: AsyncSession,
        user: User | None,
        session_id: str | None,
        domain: str,
    ) -> None:
        """Record domain usage for quota tracking."""
        await record_usage(session, user, session_id, domain)

    @staticmethod
    def get_session_id(request_headers: dict, request_cookies: dict) -> str:
        """Generate or retrieve session ID from request."""
        import uuid

        # Try to get existing session
        session_id = (
            request_cookies.get("session_id")
            or request_headers.get("x-session-id")
        )

        if session_id:
            return session_id

        # Generate new session ID
        return str(uuid.uuid4())

    @staticmethod
    async def get_anonymous_quota_limits() -> dict[str, Any]:
        """Get quota limits for anonymous users."""
        from app.config import get_settings

        settings = get_settings()
        return {
            "max_urls_per_scan": settings.MAX_URLS_PER_SCAN_UNAUTH,
            "max_domains_per_week": settings.MAX_DOMAINS_PER_WEEK_UNAUTH,
        }

    @staticmethod
    async def get_user_quota_limits(user: User) -> dict[str, Any]:
        """Get quota limits for authenticated user."""
        from app.models.user import Plan
        from sqlalchemy import select

        # This would typically query the Plan table
        # For now, return defaults based on plan type
        defaults = {
            "free": {"max_urls_per_scan": 20, "max_domains_per_week": 3},
            "lite": {"max_urls_per_scan": 100, "max_domains_per_week": 15},
            "pro": {"max_urls_per_scan": 500, "max_domains_per_week": None},
            "corporate": {"max_urls_per_scan": 1000, "max_domains_per_week": None},
        }

        return defaults.get(user.plan_type.value, defaults["free"])


async def require_scan_quota(
    session: AsyncSession,
    user: User | None,
    session_id: str | None,
    urls: list[str],
) -> None:
    """Require sufficient scan quota or raise exception."""
    allowed, error = await QuotaService.validate_scan_request(
        session, user, session_id, urls
    )

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error or "Quota limit exceeded",
        )
