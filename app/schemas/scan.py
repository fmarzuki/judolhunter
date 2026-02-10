"""Scan schemas for request/response validation."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.scan import RiskLevel, ScanStatus


class ScanCreate(BaseModel):
    """Scan creation request."""
    urls: list[str] = Field(..., min_length=1, max_length=1000)

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, urls: list[str]) -> list[str]:
        """Validate and normalize URLs."""
        from urllib.parse import urlparse

        normalized = []
        for url in urls:
            url = url.strip()
            if not url:
                continue

            # Add scheme if missing
            if not url.startswith(("http://", "https://")):
                url = "https://" + url

            # Validate URL format
            try:
                parsed = urlparse(url)
                if not parsed.netloc:
                    raise ValueError(f"Invalid URL: {url}")
                if not parsed.scheme:
                    raise ValueError(f"Missing scheme in URL: {url}")
            except Exception as e:
                raise ValueError(f"Invalid URL '{url}': {e}")

            normalized.append(url)

        if not normalized:
            raise ValueError("At least one valid URL required")

        return normalized


class ScanResponse(BaseModel):
    """Scan summary response."""
    id: int
    url: str
    domain: str
    status: ScanStatus
    risk_level: RiskLevel
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    user_id: int | None = None
    session_id: str | None = None

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class ScanDetailResponse(ScanResponse):
    """Detailed scan response with findings."""
    findings: dict[str, Any] | None
    fetch_info: dict[str, Any] | None
    error_message: str | None

    model_config = {"from_attributes": True}


class ScanStreamEvent(BaseModel):
    """Server-Sent Event for scan progress."""
    type: str  # "progress", "complete", "error"
    scan_id: int
    url: str
    message: str
    data: dict[str, Any] | None = None
    timestamp: datetime

    def sse_format(self) -> str:
        """Format as SSE message."""
        import json

        return f"data: {self.model_dump_json()}\n\n"
