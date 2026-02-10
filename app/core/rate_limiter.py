"""Rate limiting and quota enforcement."""
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.scan import UsageTracker
from app.models.user import Plan, PlanType, User

settings = get_settings()


class RateLimitError(HTTPException):
    """Custom rate limit exception."""

    def __init__(
        self,
        detail: str,
        retry_after: int | None = None,
        headers: dict | None = None,
    ):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )
        if retry_after:
            self.headers = {"Retry-After": str(retry_after)}
        elif headers:
            self.headers = headers


async def get_current_week_start() -> date:
    """Get the start date of the current week (Monday)."""
    today = date.today()
    days_since_monday = today.weekday()  # Monday = 0
    week_start = today - timedelta(days=days_since_monday)
    return week_start


async def get_user_plan(
    session: AsyncSession,
    user: User | None,
) -> Plan:
    """Get user's plan with defaults for anonymous users."""
    if user is None:
        # Anonymous user - return free plan defaults
        return Plan(
            id=0,
            name="Anonymous",
            slug=PlanType.FREE,
            max_urls_per_scan=settings.MAX_URLS_PER_SCAN_UNAUTH,
            max_domains_per_week=settings.MAX_DOMAINS_PER_WEEK_UNAUTH,
            price_monthly=None,
        )

    # Get plan from user or use free plan defaults
    plan_type = user.plan_type or PlanType.FREE

    # Query actual plan from database
    result = await session.execute(
        select(Plan).where(Plan.slug == plan_type, Plan.is_active == True),
    )
    plan = result.scalar_one_or_none()

    if plan is None:
        # Fallback to free plan defaults
        return Plan(
            id=0,
            name="Free",
            slug=PlanType.FREE,
            max_urls_per_scan=settings.MAX_URLS_PER_SCAN_FREE,
            max_domains_per_week=settings.MAX_DOMAINS_PER_WEEK_FREE,
            price_monthly=None,
        )

    return plan


async def check_quota(
    session: AsyncSession,
    user: User | None,
    session_id: str | None,
    urls: list[str],
) -> tuple[bool, str | None]:
    """Check if user/session has quota for the requested scan.

    Returns:
        (allowed, error_message)
    """
    from urllib.parse import urlparse

    plan = await get_user_plan(session, user)

    # Check 1: URL count limit
    url_count = len(urls)
    if url_count > plan.max_urls_per_scan:
        return (
            False,
            f"URL limit exceeded: {url_count} URLs (max: {plan.max_urls_per_scan})",
        )

    # Check 2: Domain weekly limit
    # Extract unique domains from URLs
    domains = set()
    for url in urls:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove www. prefix for consistency
        if domain.startswith("www."):
            domain = domain[4:]
        domains.add(domain)

    week_start = await get_current_week_start()

    # Count existing usage for this week
    conditions = [
        UsageTracker.week_start == week_start,
        UsageTracker.domain.in_(domains),
    ]

    if user:
        conditions.append(UsageTracker.user_id == user.id)
    elif session_id:
        conditions.append(UsageTracker.session_id == session_id)
    else:
        # No user and no session - deny
        return False, "Session required for quota tracking"

    # Check each domain
    for domain in domains:
        domain_conditions = conditions + [UsageTracker.domain == domain]

        result = await session.execute(
            select(func.sum(UsageTracker.scan_count)).where(*domain_conditions),
        )
        current_count = result.scalar() or 0

        if current_count >= plan.max_domains_per_week:
            return (
                False,
                f"Weekly domain limit reached for '{domain}': {current_count} (max: {plan.max_domains_per_week})",
            )

    return True, None


async def record_usage(
    session: AsyncSession,
    user: User | None,
    session_id: str | None,
    domain: str,
) -> UsageTracker:
    """Record usage of a domain for quota tracking."""
    from urllib.parse import urlparse

    # Normalize domain
    parsed = urlparse(domain if "://" in domain else f"https://{domain}")
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]

    week_start = await get_current_week_start()

    # Check for existing tracker
    conditions = [
        UsageTracker.domain == domain,
        UsageTracker.week_start == week_start,
    ]

    if user:
        conditions.append(UsageTracker.user_id == user.id)
    elif session_id:
        conditions.append(UsageTracker.session_id == session_id)
    else:
        raise ValueError("Either user or session_id required")

    result = await session.execute(
        select(UsageTracker).where(*conditions),
    )
    tracker = result.scalar_one_or_none()

    if tracker:
        # Increment count
        tracker.scan_count += 1
        await session.flush()
        return tracker
    else:
        # Create new tracker
        tracker = UsageTracker(
            user_id=user.id if user else None,
            session_id=session_id if not user else None,
            domain=domain,
            week_start=week_start,
            scan_count=1,
        )
        session.add(tracker)
        await session.flush()
        return tracker


def get_client_identifier(request: Request) -> str:
    """Get a unique identifier for the client."""
    # Try to get from header first (for trusted proxies)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    # Fall back to direct connection
    return request.client.host if request.client else "unknown"


def get_session_id(request: Request) -> str | None:
    """Get session ID from request."""
    return request.cookies.get("session_id") or request.headers.get("X-Session-ID")
