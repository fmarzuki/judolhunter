"""Async database session management."""
from collections.abc import AsyncGenerator
from typing import TypeVar

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

settings = get_settings()

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    # SQLite-specific optimizations
    connect_args={"check_same_thread": False} if settings.database_type == "sqlite" else {},
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection for async database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


T = TypeVar("T")


async def get_by_id_or_404(
    session: AsyncSession,
    model: type[T],
    id: int,
) -> T:
    """Get a record by ID or raise 404."""
    from fastapi import HTTPException

    result = await session.get(model, id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return result
