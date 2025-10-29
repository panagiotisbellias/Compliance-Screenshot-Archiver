from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class ScheduleCreate(BaseModel):
    """
    DTO for creating a schedule/job.
    """

    url: HttpUrl
    cron: str = Field(description="Cron expression in UTC")
    artifact_type: Literal["png", "pdf"] = "pdf"
    viewport_width: int = 1280
    viewport_height: int = 800
    wait_until: Literal["load", "domcontentloaded", "networkidle"] = "networkidle"
    tags: list | None = None
    retention_days: int | None = Field(default=None, ge=1)


class ScheduleOut(ScheduleCreate):
    """
    API response model for a schedule.
    """

    id: str
    enabled: bool = True


class CaptureOut(BaseModel):
    """
    API response model for a capture result.
    """

    id: str
    schedule_id: str | None = None
    sha256: str
    s3_key: str
    artifact_type: Literal["png", "pdf"] = "pdf"
    url: str
    created_at: float
    status: str = "completed"
