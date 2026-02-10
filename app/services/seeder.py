"""Database seeding service for initial data."""
import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import get_password_hash
from app.models.user import Plan, PlanType, User, UserRole


async def seed_plans(session: AsyncSession) -> None:
    """Seed subscription plans."""
    now = datetime.utcnow()
    plans_data = [
        {
            "name": "Free",
            "slug": PlanType.FREE,
            "max_urls_per_scan": 20,
            "max_domains_per_week": 3,
            "price_monthly": None,
            "features": "Basic scanning, 3 domains/week, history retention 30 days",
            "display_order": 1,
            "created_at": now,
            "updated_at": now,
        },
        {
            "name": "Lite",
            "slug": PlanType.LITE,
            "max_urls_per_scan": 100,
            "max_domains_per_week": 15,
            "price_monthly": 50000,
            "features": "100 URLs/scan, 15 domains/week, priority support, history retention 90 days",
            "display_order": 2,
            "created_at": now,
            "updated_at": now,
        },
        {
            "name": "Pro",
            "slug": PlanType.PRO,
            "max_urls_per_scan": 500,
            "max_domains_per_week": None,  # Unlimited
            "price_monthly": 150000,
            "features": "500 URLs/scan, unlimited domains, API access, priority support, unlimited history",
            "display_order": 3,
            "created_at": now,
            "updated_at": now,
        },
        {
            "name": "Corporate",
            "slug": PlanType.CORPORATE,
            "max_urls_per_scan": 1000,
            "max_domains_per_week": None,  # Unlimited
            "price_monthly": 500000,
            "features": "1000 URLs/scan, unlimited domains, API access, dedicated support, custom integrations, unlimited history",
            "display_order": 4,
            "created_at": now,
            "updated_at": now,
        },
    ]

    for plan_data in plans_data:
        # Check if plan already exists
        result = await session.execute(
            select(Plan).where(Plan.slug == plan_data["slug"])
        )
        existing = result.scalar_one_or_none()

        if not existing:
            plan = Plan(**plan_data)
            session.add(plan)

    await session.commit()
    print("✓ Plans seeded")


async def seed_admin_user(session: AsyncSession) -> None:
    """Seed admin user."""
    admin_email = "admin@judolhunter.com"
    admin_password = "Admin@123"

    result = await session.execute(
        select(User).where(User.email == admin_email)
    )
    existing = result.scalar_one_or_none()

    if not existing:
        admin = User(
            email=admin_email,
            hashed_password=get_password_hash(admin_password),
            full_name="Administrator",
            role=UserRole.ADMIN,
            plan_type=PlanType.CORPORATE,
            is_active=True,
            is_verified=True,
        )
        session.add(admin)
        await session.commit()
        print(f"✓ Admin user created: {admin_email} / {admin_password}")
    else:
        print(f"✓ Admin user already exists: {admin_email}")


async def seed_test_user(session: AsyncSession) -> None:
    """Seed test user for development."""
    test_email = "test@judolhunter.com"
    test_password = "Test@123"

    result = await session.execute(
        select(User).where(User.email == test_email)
    )
    existing = result.scalar_one_or_none()

    if not existing:
        test_user = User(
            email=test_email,
            hashed_password=get_password_hash(test_password),
            full_name="Test User",
            role=UserRole.USER,
            plan_type=PlanType.PRO,
            is_active=True,
            is_verified=True,
        )
        session.add(test_user)
        await session.commit()
        print(f"✓ Test user created: {test_email} / {test_password}")
    else:
        print(f"✓ Test user already exists: {test_email}")


async def seed_all(session: AsyncSession) -> None:
    """Seed all initial data."""
    print("Seeding database...")
    await seed_plans(session)
    await seed_admin_user(session)
    await seed_test_user(session)
    print("✓ Database seeding complete")


async def main() -> None:
    """Run seeder as standalone script."""
    from app.utils.db import async_session_maker

    settings = get_settings()

    async with async_session_maker() as session:
        await seed_all(session)


if __name__ == "__main__":
    asyncio.run(main())
