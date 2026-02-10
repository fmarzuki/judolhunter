"""Scan API endpoints with SSE streaming."""
import asyncio
import json
from collections.abc import AsyncGenerator
from collections import defaultdict
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

# In-memory storage for real-time progress messages
# Format: {scan_id: [{"message": str, "timestamp": str, "data": dict}]}
_scan_progress = defaultdict(list)


async def execute_scan(scan_id: int, url: str) -> None:
    """Background task to execute a scan."""
    from app.config import get_settings
    from app.utils.db import async_session_maker
    import traceback

    settings = get_settings()

    async with async_session_maker() as session:
        try:
            # Get scan record
            result = await session.execute(
                select(Scan).where(Scan.id == scan_id),
            )
            scan = result.scalar_one_or_none()

            if not scan:
                print(f"Scan {scan_id} not found")
                return

            # Update status to running
            scan.status = ScanStatus.RUNNING
            await session.commit()

            # Create progress callback that stores messages in memory
            progress = ProgressCallback()
            
            async def store_progress(message: str, data: dict | None = None):
                """Store progress messages in memory for SSE streaming."""
                progress_item = {
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": data
                }
                _scan_progress[scan_id].append(progress_item)
                print(f"[Scan {scan_id}] Progress: {message}")  # Debug log
            
            progress.add_callback(store_progress)

            # Run scan
            print(f"Starting scan for {url}...")
            result_data = await scan_url(url, progress)

            # Update scan with results
            scan.status = ScanStatus.COMPLETED
            scan.risk_level = result_data.get("risk_level", "unknown")
            scan.findings = result_data.get("findings", {})
            scan.fetch_info = result_data.get("fetch_info", {})
            scan.completed_at = datetime.utcnow()

            await session.commit()
            print(f"Scan {scan_id} completed: {scan.risk_level}")

        except Exception as e:
            # Mark scan as failed
            print(f"Scan {scan_id} failed: {e}")
            traceback.print_exc()
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
    user: CurrentUser = None,
):
    """Create new scan jobs for multiple URLs.

    Returns list of created scan IDs. Scans run in background.
    Works for both authenticated and anonymous users.
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
    user: CurrentUser = None,
    token: str = Query(None),
):
    """Server-Sent Events stream for real-time scan progress.
    
    Authentication can be via:
    - Authorization header (preferred)
    - token query parameter (for EventSource compatibility)
    """
    # If no user from header, try to get from token query param
    if not user and token:
        from app.core.security import decode_token
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
            if user_id:
                user_id = int(user_id)
                result = await session.execute(
                    select(User).where(User.id == user_id, User.is_active == True)
                )
                user = result.scalar_one_or_none()
                if user:
                    print(f"[SSE] Token authentication successful for user: {user.email}")
        except Exception as e:
            print(f"[SSE] Token verification failed: {e}")
            pass  # Continue as anonymous if token invalid

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events."""
        print(f"[SSE] Starting stream for scan {scan_id}, user: {user.email if user else 'anonymous'}")
        
        # Verify scan exists and user has access
        result = await session.execute(
            select(Scan).where(Scan.id == scan_id),
        )
        scan = result.scalar_one_or_none()

        if not scan:
            print(f"[SSE] Scan {scan_id} not found")
            yield "data: " + json.dumps({
                "type": "error",
                "message": "Scan not found",
            }) + "\n\n"
            return
        
        if scan.user_id != (user.id if user else None):
            print(f"[SSE] Access denied for scan {scan_id}")
            yield "data: " + json.dumps({
                "type": "error",
                "message": "Access denied",
            }) + "\n\n"
            return

        print(f"[SSE] Scan {scan_id} found, starting stream...")
        
        # Poll for updates
        last_status = None
        last_message_count = 0
        max_iterations = 600  # 5 minutes max (600 * 0.5s)

        for iteration in range(max_iterations):
            # Refresh scan from database
            await session.refresh(scan)

            # Send progress messages from in-memory storage
            if scan_id in _scan_progress:
                messages = _scan_progress[scan_id]
                if len(messages) > last_message_count:
                    print(f"[SSE] Sending {len(messages) - last_message_count} new progress messages")
                    # Send new messages
                    for msg in messages[last_message_count:]:
                        event = ScanStreamEvent(
                            type="progress",
                            scan_id=scan.id,
                            url=scan.url,
                            message=msg['message'],
                            data={
                                "status": scan.status,
                                "risk_level": scan.risk_level,
                                "step_data": msg.get('data')
                            },
                            timestamp=datetime.fromisoformat(msg['timestamp']),
                        )
                        yield event.sse_format()
                    last_message_count = len(messages)

            # Send status change events
            if scan.status != last_status:
                print(f"[SSE] Status changed to: {scan.status}")
                event = ScanStreamEvent(
                    type="status",
                    scan_id=scan.id,
                    url=scan.url,
                    message=f"Status berubah: {scan.status}",
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
                print(f"[SSE] Scan {scan_id} finished with status: {scan.status}")
                final_event = ScanStreamEvent(
                    type="complete" if scan.status == ScanStatus.COMPLETED else "error",
                    scan_id=scan.id,
                    url=scan.url,
                    message="✓ Scan selesai" if scan.status == ScanStatus.COMPLETED else f"✗ Scan gagal: {scan.error_message}",
                    data={
                        "status": scan.status,
                        "risk_level": scan.risk_level,
                        "findings": scan.findings,
                    },
                    timestamp=datetime.utcnow(),
                )
                yield final_event.sse_format()
                
                # Clean up progress messages from memory
                if scan_id in _scan_progress:
                    del _scan_progress[scan_id]
                
                break

            await asyncio.sleep(0.5)  # Poll every 500ms for better responsiveness

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
