from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ...auth.deps import can_access_user_resource, require_operator, require_viewer

# Removed direct import of processor to avoid Playwright dependency in API Lambda
from ...domain.models import CaptureOut
from ...storage.dynamo import delete_capture, get_capture, list_captures_by_user
from ...storage.s3 import delete_object, presign_download

router: APIRouter = APIRouter()
logger = logging.getLogger(__name__)

# Pre-instantiated dependencies to avoid B008 lint issues
_viewer_dep = Depends(require_viewer)
_operator_dep = Depends(require_operator)


@router.get("", response_model=list)
async def list_captures(
    limit: int = Query(default=50, ge=1, le=100),
    last_key: str = Query(default=None),
    user_info: dict[str, str] = _viewer_dep,
):
    """
    List captures for the authenticated user.

    Args:
        limit: Maximum number of captures to return.
        last_key: Pagination token from previous request.
        user_info: User authentication info.

    Returns:
        list[CaptureOut]: User's captures.
    """
    user_id = user_info.get("sub", "unknown")

    # Parse pagination token if provided
    last_evaluated_key = None
    if last_key:
        try:
            import json

            last_evaluated_key = json.loads(last_key)
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=400, detail="Invalid pagination token") from e

    # Fetch captures from DynamoDB
    result = list_captures_by_user(
        user_id=user_id,
        limit=limit,
        last_evaluated_key=last_evaluated_key,
    )

    # Convert to response models
    captures = []
    for item in result["items"]:
        captures.append(
            CaptureOut(
                id=item["capture_id"],
                sha256=item["sha256"],
                s3_key=item["s3_key"],
                artifact_type=item["artifact_type"],
                url=item["url"],
                created_at=float(item["created_at"]),
                status=item.get("status", "completed"),
            )
        )

    # No mock data - show real captures only

    return captures


@router.get("/{capture_id}", response_model=CaptureOut)
async def get_capture_by_id(
    capture_id: str,
    user_info: dict[str, str] = _viewer_dep,
) -> CaptureOut:
    """
    Get a specific capture by ID.

    Args:
        capture_id: Capture ID.
        user_info: User authentication info.

    Returns:
        CaptureOut: Capture details.
    """
    capture = get_capture(capture_id)

    if not capture:
        raise HTTPException(status_code=404, detail="Capture not found")

    # Verify user has access to this capture
    if not can_access_user_resource(user_info, capture["user_id"]):
        raise HTTPException(status_code=403, detail="Access denied")

    return CaptureOut(
        id=capture["capture_id"],
        sha256=capture["sha256"],
        s3_key=capture["s3_key"],
        artifact_type=capture["artifact_type"],
        url=capture["url"],
        created_at=float(capture["created_at"]),
        status=capture.get("status", "completed"),
    )


@router.get("/{capture_id}/download")
async def download_capture(
    capture_id: str,
    user_info: dict[str, str] = _viewer_dep,
) -> dict[str, str]:
    """
    Get a presigned URL to download a capture.

    Args:
        capture_id: Capture ID.
        user_info: User authentication info.

    Returns:
        dict: Download URL and metadata.
    """
    capture = get_capture(capture_id)

    # No mock data - only real captures

    if not capture:
        raise HTTPException(status_code=404, detail="Capture not found")

    # Verify user has access
    if not can_access_user_resource(user_info, capture["user_id"]):
        raise HTTPException(status_code=403, detail="Access denied")

    # Generate presigned URL with version ID if available
    version_id = capture.get("metadata", {}).get("s3_version_id")
    download_url = presign_download(capture["s3_key"], version_id=version_id)

    return {
        "download_url": download_url,
        "expires_in": "900",  # 15 minutes
        "filename": f"{capture_id}.{capture['artifact_type']}",
        "content_type": "application/pdf" if capture["artifact_type"] == "pdf" else "image/png",
    }


@router.post("/trigger", response_model=dict[str, Any])
async def trigger_capture(
    url: str,
    artifact_type: str = Query(default="pdf", pattern="^(png|pdf)$"),
    user_info: dict[str, str] = _operator_dep,
) -> dict[str, Any]:
    """
    Trigger an on-demand capture with immediate processing (synchronous).

    Args:
        url: Target URL to capture.
        artifact_type: 'png' or 'pdf'.
        user_info: User authentication info.

    Returns:
        dict: Completed capture details with download info.
    """
    import uuid

    user_id = user_info.get("sub", "unknown")
    capture_id = str(uuid.uuid4())

    try:
        logger.info(f"Processing synchronous capture {capture_id} for {url}")

        # Import and use the capture processor directly
        from ...capture_engine.processor import process_capture_request

        result = await process_capture_request(
            url=url,
            artifact_type=artifact_type,
            user_id=user_id,
            metadata={"triggered_via": "api"},
            capture_id=capture_id,
        )

        if result.get("status") == "completed":
            logger.info(f"Successfully archived {capture_id}: {result['s3_key']}")

            # Return immediate success response
            return {
                "capture_id": capture_id,
                "status": "completed",
                "url": url,
                "artifact_type": artifact_type,
                "s3_key": result["s3_key"],
                "sha256": result["sha256"],
                "message": "Screenshot archived successfully",
            }
        else:
            logger.error(f"Capture failed for {capture_id}: {result.get('error', 'Unknown error')}")
            raise HTTPException(
                status_code=500,
                detail=f"Capture failed: {result.get('error', 'Processing failed')}",
            )

    except Exception as e:
        logger.error(f"Failed to process capture {capture_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to archive screenshot: {str(e)}"
        ) from e


@router.post("/verify", response_model=dict[str, Any])
async def verify_capture(
    sha256: str,
    user_info: dict[str, str] = _viewer_dep,
) -> dict[str, Any]:
    """
    Verify a capture by its SHA-256 hash.

    Args:
        sha256: SHA-256 hash to verify.
        user_info: User authentication info.

    Returns:
        dict: Verification result.
    """
    from ...storage.dynamo import get_capture_by_hash
    from ...storage.s3 import verify_object_lock

    # Find capture by hash
    capture = get_capture_by_hash(sha256)

    if not capture:
        return {
            "verified": False,
            "reason": "No capture found with this hash",
            "sha256": sha256,
        }

    # Verify Object Lock is still in place
    object_locked = verify_object_lock(capture["s3_key"])

    return {
        "verified": True,
        "capture_id": capture["capture_id"],
        "url": capture["url"],
        "artifact_type": capture["artifact_type"],
        "created_at": float(capture["created_at"]),
        "object_lock_verified": object_locked,
        "sha256": sha256,
    }


@router.delete("/{capture_id}")
async def delete_capture_by_id(
    capture_id: str,
    user_info: dict[str, str] = _operator_dep,
) -> dict[str, str]:
    """
    Delete a capture and its associated S3 object.

    Args:
        capture_id: Capture ID to delete.
        user_info: User authentication info.

    Returns:
        dict: Deletion confirmation message.
    """
    # Get the capture details first
    capture = get_capture(capture_id)

    if not capture:
        raise HTTPException(status_code=404, detail="Capture not found")

    # Verify user has access to delete this capture
    if not can_access_user_resource(user_info, capture["user_id"]):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get version ID if available for S3 deletion
    version_id = capture.get("metadata", {}).get("s3_version_id")

    try:
        # Delete from S3 first
        s3_deleted = delete_object(capture["s3_key"], version_id=version_id)
        if not s3_deleted:
            logger.warning(
                f"Failed to delete S3 object for capture {capture_id}, continuing with DynamoDB deletion"
            )

        # Delete from DynamoDB
        db_deleted = delete_capture(capture_id)
        if not db_deleted:
            raise HTTPException(
                status_code=500, detail="Failed to delete capture record from database"
            )

        logger.info(
            f"Successfully deleted capture {capture_id} (S3: {s3_deleted}, DB: {db_deleted})"
        )
        return {
            "message": f"Capture {capture_id} deleted successfully",
            "s3_deleted": str(s3_deleted),
            "db_deleted": str(db_deleted),
        }

    except Exception as e:
        logger.error(f"Error deleting capture {capture_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete capture: {str(e)}") from e
