"""Create admin and test users using bcrypt directly."""
import asyncio
from datetime import datetime

import bcrypt
from sqlalchemy import select

from app.utils.db import async_session_maker
from app.models.user import User, UserRole, PlanType


def hash_password(password: str) -> str:
    """Hash password using bcrypt directly."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


async def create_users():
    """Create admin and test users."""
    now = datetime.utcnow()
    async with async_session_maker() as session:
        # Check if admin exists
        result = await session.execute(
            select(User).where(User.email == "admin@judolhunter.com")
        )
        admin_exists = result.scalar_one_or_none()

        if not admin_exists:
            admin = User(
                email="admin@judolhunter.com",
                hashed_password=hash_password("Admin@123"),
                full_name="Administrator",
                role=UserRole.ADMIN,
                plan_type=PlanType.CORPORATE,
                is_active=True,
                is_verified=True,
                created_at=now,
                updated_at=now,
            )
            session.add(admin)
            print("✓ Admin user created: admin@judolhunter.com / Admin@123")
        else:
            print("✓ Admin user already exists")

        # Check if test user exists
        result = await session.execute(
            select(User).where(User.email == "test@judolhunter.com")
        )
        test_exists = result.scalar_one_or_none()

        if not test_exists:
            test_user = User(
                email="test@judolhunter.com",
                hashed_password=hash_password("Test@123"),
                full_name="Test User",
                role=UserRole.USER,
                plan_type=PlanType.PRO,
                is_active=True,
                is_verified=True,
                created_at=now,
                updated_at=now,
            )
            session.add(test_user)
            print("✓ Test user created: test@judolhunter.com / Test@123")
        else:
            print("✓ Test user already exists")

        await session.commit()
        print("✓ Users setup complete")


if __name__ == "__main__":
    asyncio.run(create_users())
