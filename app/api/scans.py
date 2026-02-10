"""Scan API endpoints with SSE streaming."""
import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiter import get_session_id
from app.dependencies import AuthUser, CurrentUser, DbSession
from app.models.scan import Scan, ScanStatus
from app.models.user import User
from app.schemas.scan import ScanCreate, ScanDetailResponse, ScanResponse, ScanStreamEvent
from app.services.quota_service import QuotaService, require_scan_quota
from app.services.scanner import ProgressCallback, scan_url

router = APIRouter(prefix="/api/scans", tags=["Scans"])


async def execute_scan(scan_id: int, url: str) -> None:
    """Background task to execute a scan."""
    from app.config import get_settings
    from app.utils.db import async_session_maker

    settings = get_settings()

    async with async_session_maker() as session:
        try:
            # Get scan record
            result = await session.execute(
                select(Scan).where(Scan.id == scan_id),
            )
            scan = result.scalar_one_or_none()

            if not scan:
                return

            # Update status to running
            scan.status = ScanStatus.RUNNING
            await session.commit()

            # Create progress callback for SSE
            progress = ProgressCallback()

            # Run scan
            result_data = await scan_url(url, progress)

            # Update scan with results
            scan.status = ScanStatus.COMPLETED
            scan.risk_level = result_data.get("risk_level", "unknown")
            scan.findings = result_data.get("findings", {})
            scan.fetch_info = result_data.get("fetch_info", {})
            scan.completed_at = datetime.utcnow()

            await session.commit()

        except Exception as e:
            # Mark scan as failed
            result = await session.execute(
                select(Scan).where(Scan.id == scan_id),
            )
            scan = result.scalar_one_or_none()
            if scan:
                scan.status = ScanStatus.FAILED
                scan.error_message = str(e)
                scan.completed_at = datetime.utcnow()
            await session.commit()


@router.post("", response_model=list[ScanResponse], status_code=202)
async def create_scan(
    data: ScanCreate,
    background_tasks: BackgroundTasks,
    session: DbSession,
    user: CurrentUser,
):
    """Create new scan jobs for multiple URLs.

    Returns list of created scan IDs. Scans run in background.
    """
    # Get or create session ID for anonymous users
    sess_id = None
    if user is None:
        # Generate a session ID for anonymous users
        import uuid
        sess_id = str(uuid.uuid4())

    # Validate quota
    await require_scan_quota(session, user, sess_id, data.urls)

    # Create scan jobs
    scans = []
    domains_to_track = set()

    for url in data.urls:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        scan = await QuotaService.create_scan_job(session, user, sess_id, url)
        scans.append(scan)
        domains_to_track.add(domain)

        # Queue background scan
        background_tasks.add_task(execute_scan, scan.id, url)

    # Record usage for all domains
    for domain in domains_to_track:
        await QuotaService.record_domain_usage(session, user, sess_id, domain)

    await session.commit()

    return scans


@router.get("", response_model=list[ScanResponse])
async def list_scans(
    session: DbSession,
    user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """List scans for the current user."""
    query = select(Scan)

    if user:
        query = query.where(Scan.user_id == user.id)
    else:
        # Anonymous users - empty list (would need session filtering)
        return []

    query = query.order_by(Scan.started_at.desc()).offset(skip).limit(limit)

    result = await session.execute(query)
    scans = result.scalars().all()

    return scans


@router.get("/{scan_id}", response_model=ScanDetailResponse)
async def get_scan(
    scan_id: int,
    session: DbSession,
    user: CurrentUser,
):
    """Get detailed scan results."""
    result = await session.execute(
        select(Scan).where(Scan.id == scan_id),
    )
    scan = result.scalar_one_or_none()

    if not scan:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Scan not found")

    # Check ownership
    if scan.user_id != (user.id if user else None):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Access denied")

    return scan


@router.get("/{scan_id}/stream")
async def stream_scan_progress(
    scan_id: int,
    session: DbSession,
    user: CurrentUser,
):
    """Server-Sent Events stream for real-time scan progress."""

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events."""
        # Verify scan exists and user has access
        result = await session.execute(
            select(Scan).where(Scan.id == scan_id),
        )
        scan = result.scalar_one_or_none()

        if not scan or scan.user_id != (user.id if user else None):
            yield "data: " + json.dumps({
                "type": "error",
                "message": "Scan not found or access denied",
            }) + "\n\n"
            return

        # Poll for updates
        last_status = None
        max_iterations = 300  # 5 minutes max

        for _ in range(max_iterations):
            # Refresh scan from database
            await session.refresh(scan)

            if scan.status != last_status:
                event = ScanStreamEvent(
                    type="progress",
                    scan_id=scan.id,
                    url=scan.url,
                    message=f"Scan {scan.status}",
                    data={
                        "status": scan.status,
                        "risk_level": scan.risk_level,
                    },
                    timestamp=datetime.utcnow(),
                )
                yield event.sse_format()
                last_status = scan.status

            # Stop if completed or failed
            if scan.status in (ScanStatus.COMPLETED, ScanStatus.FAILED):
                final_event = ScanStreamEvent(
                    type="complete" if scan.status == ScanStatus.COMPLETED else "error",
                    scan_id=scan.id,
                    url=scan.url,
                    message="Scan completed" if scan.status == ScanStatus.COMPLETED else f"Scan failed: {scan.error_message}",
                    data={
                        "status": scan.status,
                        "risk_level": scan.risk_level,
                        "findings": scan.findings,
                    },
                    timestamp=datetime.utcnow(),
                )
                yield final_event.sse_format()
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/{scan_id}")
async def delete_scan(
    scan_id: int,
    session: DbSession,
    user: AuthUser,
):
    """Delete a scan record."""
    from fastapi import HTTPException

    result = await session.execute(
        select(Scan).where(Scan.id == scan_id),
    )
    scan = result.scalar_one_or_none()

    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    if scan.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    await session.delete(scan)
    await session.commit()

    return {"message": "Scan deleted"}
