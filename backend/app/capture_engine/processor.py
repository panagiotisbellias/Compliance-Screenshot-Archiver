"""Core capture processing functionality."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from ..core.logging import jlog
from ..storage.dynamo import CaptureData, create_capture
from ..storage.s3 import upload_artifact

# Import moved inside function to avoid Playwright dependency at module level

logger = logging.getLogger(__name__)


async def process_capture_request(
    url: str,
    artifact_type: str = "pdf",
    user_id: str = "system",
    metadata: Optional[dict[str, Any]] = None,
    capture_id: Optional[str] = None,  # Allow capture_id to be passed in
) -> dict[str, Any]:
    """
    Process a single capture request end-to-end.

    Args:
        url: Target URL to capture.
        artifact_type: Type of artifact (pdf/png).
        user_id: ID of requesting user.
        metadata: Additional metadata.
        capture_id: Optional capture ID to use (generates one if not provided).

    Returns:
        dict: Capture result with S3 and DynamoDB details.
    """
    # ONLY use Playwright - no fallbacks
    try:
        # First test basic playwright import
        import playwright

        # Get version safely (may not be available in all installations)
        try:
            version = getattr(playwright, "__version__", "unknown")
        except:
            version = "unknown"
        jlog(logger, "playwright_version", version=version, level="INFO")

        # Test async_playwright import
        from playwright.async_api import async_playwright

        jlog(
            logger,
            "playwright_async_import",
            message="async_playwright imported successfully",
            level="INFO",
        )

        # Import our capture engine
        from .engine import capture_webpage

        jlog(
            logger,
            "capture_engine",
            message="Using Playwright engine for real browser screenshots",
            level="INFO",
        )
    except ImportError as e:
        import sys
        import os

        error_msg = f"CRITICAL: Playwright import failed: {str(e)}"
        jlog(
            logger,
            "playwright_import_error",
            error=error_msg,
            python_path=sys.path,
            pythonpath_env=os.environ.get("PYTHONPATH"),
            working_dir=os.getcwd(),
            level="ERROR",
        )
        raise RuntimeError(f"Playwright is required but not available: {str(e)}")

    # Use provided capture_id or generate new one
    if capture_id is None:
        capture_id = str(uuid.uuid4())

    try:
        # Step 1: Capture the webpage
        jlog(logger, "capture_start", capture_id=capture_id, url=url, artifact_type=artifact_type)

        # Test Playwright browser availability before capture
        import os

        playwright_browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/ms-playwright")
        jlog(
            logger,
            "playwright_env",
            browsers_path=playwright_browsers_path,
            browsers_exist=os.path.exists(playwright_browsers_path),
            level="INFO",
        )

        capture_result = await capture_webpage(url, artifact_type)
        sha256_hash = capture_result["sha256"]
        artifact_data = capture_result["data"]

        # Step 2: Upload to S3 with Object Lock
        s3_key = f"captures/{capture_id}.{artifact_type}"
        upload_metadata = {
            "url": url,
            "artifact-type": artifact_type,
            "capture-id": capture_id,
            "user-id": user_id,
        }
        if metadata:
            upload_metadata.update({f"custom-{k}": str(v) for k, v in metadata.items()})

        s3_result = upload_artifact(
            key=s3_key,
            data=artifact_data,
            metadata=upload_metadata,
        )

        jlog(
            logger,
            "s3_upload_complete",
            capture_id=capture_id,
            s3_key=s3_key,
            version_id=s3_result["version_id"],
            retention_until=s3_result["retention_until"],
        )

        # Step 3: Store record in DynamoDB
        capture_data = CaptureData(
            capture_id=capture_id,
            url=url,
            sha256=sha256_hash,
            s3_key=s3_key,
            artifact_type=artifact_type,
            user_id=user_id,
            metadata={
                "s3_version_id": s3_result["version_id"],
                "content_length": capture_result["content_length"],
                "retention_until": s3_result["retention_until"],
                **(metadata or {}),
            },
        )
        ddb_result = create_capture(capture_data)

        jlog(
            logger,
            "capture_complete",
            capture_id=capture_id,
            sha256=sha256_hash,
            s3_key=s3_key,
            status="success",
        )

        return {
            "capture_id": capture_id,
            "url": url,
            "sha256": sha256_hash,
            "s3_key": s3_key,
            "artifact_type": artifact_type,
            "user_id": user_id,
            "status": "completed",
            "s3_details": s3_result,
            "ddb_record": ddb_result,
        }

    except Exception as e:
        error_msg = str(e)
        import traceback

        stack_trace = traceback.format_exc()

        jlog(
            logger,
            "capture_failed",
            capture_id=capture_id,
            url=url,
            error=error_msg,
            level="ERROR",
        )

        # Don't expose internal details in the response
        return {
            "capture_id": capture_id,
            "url": url,
            "status": "failed",
            "error": "Capture failed - check logs for details",
            "internal_error": error_msg,
            "stack_trace": stack_trace,
        }
