"""Admin API endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import AdminUser, DbSession
from app.models.scan import Scan, UsageTracker
from app.models.user import Plan, PlanType, User, UserRole
from app.schemas.user import PlanResponse, UserResponse

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/stats")
async def get_admin_stats(
    session: DbSession,
    admin: AdminUser,
):
    """Get platform-wide statistics."""
    # Count users by plan
    user_counts = {}
    for plan_type in PlanType:
        result = await session.execute(
            select(User).where(User.plan_type == plan_type)
        )
        count = len(result.scalars().all())
        user_counts[plan_type.value] = count

    # Count scans by status
    from app.models.scan import ScanStatus

    scan_counts = {}
    for scan_status in ScanStatus:
        result = await session.execute(
            select(Scan).where(Scan.status == scan_status)
        )
        count = len(result.scalars().all())
        scan_counts[scan_status.value] = count

    # Total counts
    total_users = await session.execute(select(User))
    total_users_count = len(total_users.scalars().all())

    total_scans = await session.execute(select(Scan))
    total_scans_count = len(total_scans.scalars().all())

    return {
        "users": {
            "total": total_users_count,
            "by_plan": user_counts,
        },
        "scans": {
            "total": total_scans_count,
            "by_status": scan_counts,
        },
    }


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    session: DbSession,
    admin: AdminUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    plan_type: PlanType | None = None,
):
    """List all users with optional filtering."""
    query = select(User)

    if plan_type:
        query = query.where(User.plan_type == plan_type)

    query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)

    result = await session.execute(query)
    users = result.scalars().all()

    return users


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    session: DbSession,
    admin: AdminUser,
):
    """Get detailed user information."""
    from fastapi import HTTPException

    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    data: dict,
    session: DbSession,
    admin: AdminUser,
):
    """Update user information (admin only)."""
    from fastapi import HTTPException

    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update allowed fields
    if "plan_type" in data:
        user.plan_type = PlanType(data["plan_type"])
    if "plan_expires_at" in data:
        from datetime import datetime
        if data["plan_expires_at"]:
            user.plan_expires_at = datetime.fromisoformat(data["plan_expires_at"])
        else:
            user.plan_expires_at = None
    if "is_active" in data:
        user.is_active = data["is_active"]
    if "is_verified" in data:
        user.is_verified = data["is_verified"]
    if "role" in data:
        user.role = UserRole(data["role"])

    await session.commit()
    await session.refresh(user)

    return user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    session: DbSession,
    admin: AdminUser,
):
    """Delete a user (admin only)."""
    from fastapi import HTTPException

    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    await session.delete(user)
    await session.commit()

    return {"message": "User deleted"}


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    session: DbSession,
    admin: AdminUser,
):
    """List all subscription plans."""
    result = await session.execute(
        select(Plan).order_by(Plan.display_order)
    )
    plans = result.scalars().all()

    return plans


@router.post("/plans", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    data: dict,
    session: DbSession,
    admin: AdminUser,
):
    """Create a new subscription plan."""
    plan = Plan(
        name=data["name"],
        slug=PlanType(data["slug"]),
        max_urls_per_scan=data["max_urls_per_scan"],
        max_domains_per_week=data["max_domains_per_week"],
        price_monthly=data.get("price_monthly"),
        features=data.get("features"),
        display_order=data.get("display_order", 0),
        is_active=data.get("is_active", True),
    )

    session.add(plan)
    await session.commit()
    await session.refresh(plan)

    return plan


@router.put("/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: int,
    data: dict,
    session: DbSession,
    admin: AdminUser,
):
    """Update a subscription plan."""
    from fastapi import HTTPException

    result = await session.execute(
        select(Plan).where(Plan.id == plan_id)
    )
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Update fields
    if "name" in data:
        plan.name = data["name"]
    if "max_urls_per_scan" in data:
        plan.max_urls_per_scan = data["max_urls_per_scan"]
    if "max_domains_per_week" in data:
        plan.max_domains_per_week = data["max_domains_per_week"]
    if "price_monthly" in data:
        plan.price_monthly = data["price_monthly"]
    if "features" in data:
        plan.features = data["features"]
    if "display_order" in data:
        plan.display_order = data["display_order"]
    if "is_active" in data:
        plan.is_active = data["is_active"]

    await session.commit()
    await session.refresh(plan)

    return plan


@router.delete("/plans/{plan_id}")
async def delete_plan(
    plan_id: int,
    session: DbSession,
    admin: AdminUser,
):
    """Delete a subscription plan."""
    from fastapi import HTTPException

    result = await session.execute(
        select(Plan).where(Plan.id == plan_id)
    )
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    await session.delete(plan)
    await session.commit()

    return {"message": "Plan deleted"}


@router.get("/scans")
async def list_all_scans(
    session: DbSession,
    admin: AdminUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: str | None = None,
):
    """List all scans across all users."""
    query = select(Scan)

    if status:
        query = query.where(Scan.status == status)

    query = query.order_by(Scan.started_at.desc()).offset(skip).limit(limit)

    result = await session.execute(query)
    scans = result.scalars().all()

    return [
        {
            "id": s.id,
            "url": s.url,
            "domain": s.domain,
            "status": s.status,
            "risk_level": s.risk_level,
            "user_id": s.user_id,
            "started_at": s.started_at,
            "completed_at": s.completed_at,
        }
        for s in scans
    ]
