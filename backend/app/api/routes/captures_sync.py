from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ...auth.deps import require_operator
from ...domain.models import CaptureOut

router: APIRouter = APIRouter()
logger = logging.getLogger(__name__)

# Pre-instantiated dependencies to avoid B008 lint issues
_operator_dep = Depends(require_operator)


@router.post("/sync", response_model=dict[str, Any])
async def trigger_capture_sync(
    url: str,
    artifact_type: str = Query(default="pdf", pattern="^(png|pdf)$"),
    user_info: dict[str, str] = _operator_dep,
) -> dict[str, Any]:
    """
    Trigger a synchronous capture (bypasses SQS for testing).

    Args:
        url: Target URL to capture.
        artifact_type: 'png' or 'pdf'.
        user_info: User authentication info.

    Returns:
        dict: Capture result with download info.
    """
    import uuid

    user_id = user_info.get("sub", "unknown")
    capture_id = str(uuid.uuid4())

    try:
        from ...capture_engine.processor import process_capture_request

        logger.info(f"Starting synchronous capture {capture_id} for {url}")

        result = await process_capture_request(
            url=url,
            artifact_type=artifact_type,
            user_id=user_id,
            metadata={"triggered_via": "sync_api"},
            capture_id=capture_id,
        )

        if result.get("status") == "completed":
            # Generate download URL immediately
            from ...storage.s3 import presign_download

            s3_version_id = result.get("s3_details", {}).get("version_id")
            download_url = presign_download(result["s3_key"], version_id=s3_version_id)

            return {
                "capture_id": capture_id,
                "status": "completed",
                "url": url,
                "artifact_type": artifact_type,
                "s3_key": result["s3_key"],
                "sha256": result["sha256"],
                "download_url": download_url,
                "content_type": "application/pdf" if artifact_type == "pdf" else "image/png",
            }
        else:
            raise HTTPException(
                status_code=500, detail=f"Capture failed: {result.get('error', 'Unknown error')}"
            )

    except Exception as e:
        logger.error(f"Synchronous capture failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Capture processing failed: {str(e)}") from e
