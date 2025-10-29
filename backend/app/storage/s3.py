from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Constants
MAX_PRESIGN_TTL_SECONDS = 900  # 15 minutes max for security
DEFAULT_RETENTION_DAYS = 2555  # ~7 years default


def s3_client() -> Any:
    """
    Create an S3 client with recommended defaults.

    Returns:
        botocore.client.S3: S3 client.
    """
    return boto3.client(
        "s3",
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "virtual"}, signature_version="s3v4"),
    )


def upload_artifact(
    key: str,
    data: bytes,
    metadata: dict[str, str] | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> dict[str, Any]:
    """
    Upload an artifact to S3 with Object Lock in Compliance mode.

    Args:
        key: S3 object key.
        data: Binary data to upload.
        metadata: Optional metadata to attach.
        retention_days: Retention period in days.

    Returns:
        dict: Upload result with version ID and Object Lock details.
    """
    client = s3_client()

    # Calculate retention date
    retention_until = datetime.now(UTC) + timedelta(days=retention_days)

    # Prepare metadata
    if metadata is None:
        metadata = {}

    # Add compliance metadata
    metadata.update(
        {
            "captured-at": str(datetime.now(UTC).isoformat()),
            "retention-until": str(retention_until.isoformat()),
        }
    )

    # Determine content type based on file extension
    content_type = "application/octet-stream"  # Default
    if key.lower().endswith(".pdf"):
        content_type = "application/pdf"
    elif key.lower().endswith(".png"):
        content_type = "image/png"
    elif key.lower().endswith(".jpg") or key.lower().endswith(".jpeg"):
        content_type = "image/jpeg"

    try:
        # Prepare upload parameters
        put_params = {
            "Bucket": settings.s3_bucket_artifacts,
            "Key": key,
            "Body": data,
            "Metadata": metadata,
            "ContentType": content_type,  # Set proper MIME type
        }

        # Add encryption parameters if KMS key is configured
        if settings.kms_key_arn:
            put_params.update(
                {
                    "ServerSideEncryption": "aws:kms",
                    "SSEKMSKeyId": settings.kms_key_arn,
                }
            )
        else:
            # Use bucket default encryption (AES256)
            put_params["ServerSideEncryption"] = "AES256"

        # Add Object Lock parameters only in production environment
        if settings.env != "dev":
            put_params.update(
                {
                    "ObjectLockMode": "COMPLIANCE",
                    "ObjectLockRetainUntilDate": retention_until,
                }
            )
            logger.info(f"Using Object Lock in {settings.env} environment")
        else:
            logger.info(f"Skipping Object Lock in {settings.env} environment")

        # Upload artifact
        response = client.put_object(**put_params)

        if settings.env != "dev":
            logger.info(
                f"Uploaded artifact to s3://{settings.s3_bucket_artifacts}/{key} "
                f"with Object Lock until {retention_until.isoformat()} "
                f"and content-type {content_type}"
            )
        else:
            logger.info(
                f"Uploaded artifact to s3://{settings.s3_bucket_artifacts}/{key} "
                f"with content-type {content_type} "
                f"(dev environment - no Object Lock)"
            )

        return {
            "bucket": settings.s3_bucket_artifacts,
            "key": key,
            "version_id": response.get("VersionId"),
            "etag": response.get("ETag"),
            "content_type": content_type,
            "retention_until": retention_until.isoformat(),
            "object_lock_mode": "COMPLIANCE",
        }

    except ClientError as e:
        logger.error(f"Failed to upload artifact: {e}")
        raise


def get_artifact(key: str, version_id: str | None = None) -> bytes:
    """
    Retrieve an artifact from S3.

    Args:
        key: S3 object key.
        version_id: Optional specific version to retrieve.

    Returns:
        bytes: The artifact data.
    """
    client = s3_client()

    params = {
        "Bucket": settings.s3_bucket_artifacts,
        "Key": key,
    }

    # Try with version ID first if provided
    if version_id:
        try:
            versioned_params = params.copy()
            versioned_params["VersionId"] = version_id
            response = client.get_object(**versioned_params)
            data: bytes = response["Body"].read()
            logger.info(f"Retrieved artifact {key} with version {version_id}")
            return data
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ["NoSuchVersion", "NoSuchKey", "NotFound", "404"]:
                logger.warning(
                    f"Version {version_id} not found for {key}, falling back to latest version"
                )
                # Fall through to try without version ID
            else:
                logger.error(f"Failed to retrieve artifact with version ID: {e}")
                raise

    try:
        response = client.get_object(**params)
        data = response["Body"].read()
        logger.info(f"Retrieved artifact {key} (latest version)")
        return data
    except ClientError as e:
        logger.error(f"Failed to retrieve artifact: {e}")
        raise


def get_artifact_metadata(key: str, version_id: str | None = None) -> dict[str, Any]:
    """
    Get metadata for an artifact without downloading it.

    Args:
        key: S3 object key.
        version_id: Optional specific version.

    Returns:
        dict: Object metadata including size, hash, and lock status.
    """
    client = s3_client()

    params = {
        "Bucket": settings.s3_bucket_artifacts,
        "Key": key,
    }

    # Try with version ID first if provided
    if version_id:
        try:
            versioned_params = params.copy()
            versioned_params["VersionId"] = version_id
            response = client.head_object(**versioned_params)
            logger.info(f"Retrieved metadata for {key} with version {version_id}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ["NoSuchVersion", "NoSuchKey", "NotFound", "404"]:
                logger.warning(
                    f"Version {version_id} not found for {key}, falling back to latest version"
                )
                # Fall through to try without version ID
                response = client.head_object(**params)
                logger.info(f"Retrieved metadata for {key} (latest version)")
            else:
                logger.error(f"Failed to get artifact metadata with version ID: {e}")
                raise
    else:
        try:
            response = client.head_object(**params)
            logger.info(f"Retrieved metadata for {key} (latest version)")
        except ClientError as e:
            logger.error(f"Failed to get artifact metadata: {e}")
            raise

    return {
        "key": key,
        "size": response.get("ContentLength"),
        "etag": response.get("ETag"),
        "last_modified": response.get("LastModified"),
        "version_id": response.get("VersionId"),
        "object_lock_mode": response.get("ObjectLockMode"),
        "object_lock_retain_until": response.get("ObjectLockRetainUntilDate"),
        "metadata": response.get("Metadata", {}),
    }


def presign_download(key: str, expires: int | None = None, version_id: str | None = None) -> str:
    """
    Generate a presigned URL for downloading an artifact.

    Args:
        key: Object key.
        expires: Expiry seconds (default from settings).
        version_id: Optional specific version ID to download.

    Returns:
        str: Presigned URL.
    """
    client = s3_client()
    ttl = expires or settings.presign_ttl_seconds

    # Ensure TTL doesn't exceed 15 minutes per security requirements
    if ttl > MAX_PRESIGN_TTL_SECONDS:
        logger.warning(
            f"Requested TTL {ttl}s exceeds 15 minutes, capping at {MAX_PRESIGN_TTL_SECONDS}s"
        )
        ttl = MAX_PRESIGN_TTL_SECONDS

    # Prepare parameters for presigned URL
    params = {"Bucket": settings.s3_bucket_artifacts, "Key": key}

    # Try with version ID first if provided, but fall back if it doesn't exist
    if version_id:
        try:
            # Test if the version exists by doing a head request
            versioned_params = params.copy()
            versioned_params["VersionId"] = version_id
            client.head_object(**versioned_params)

            # Version exists, use it in presigned URL
            params["VersionId"] = version_id
            logger.info(f"Generating presigned URL for {key} version {version_id}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ["NoSuchVersion", "NoSuchKey", "NotFound", "404"]:
                logger.warning(
                    f"Version {version_id} not found for {key}, generating URL for latest version"
                )
                # Don't add VersionId to params, will use latest
            else:
                logger.warning(
                    f"Failed to verify version {version_id} for {key}: {e} - "
                    "falling back to latest version"
                )
                # Still try to generate URL without version ID
    else:
        logger.info(f"Generating presigned URL for {key} (latest version)")

    url: str = client.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=ttl,
    )
    return url


def verify_object_lock(key: str) -> bool:
    """
    Verify that an object has Object Lock in Compliance mode.

    Args:
        key: S3 object key.

    Returns:
        bool: True if properly locked, False otherwise.
    """
    try:
        metadata = get_artifact_metadata(key)
        return metadata.get("object_lock_mode") == "COMPLIANCE"
    except ClientError:
        return False


def delete_object(key: str, version_id: str | None = None) -> bool:
    """
    Delete an object from S3.

    Args:
        key: S3 object key.
        version_id: Optional version ID for versioned objects.

    Returns:
        bool: True if deleted successfully, False otherwise.
    """
    s3 = s3_client()
    bucket = settings.s3_bucket_artifacts

    try:
        delete_params = {"Bucket": bucket, "Key": key}
        if version_id:
            delete_params["VersionId"] = version_id

        s3.delete_object(**delete_params)
        logger.info(
            f"Deleted S3 object: {key}" + (f" (version: {version_id})" if version_id else "")
        )
        return True
    except ClientError as e:
        logger.error(f"Failed to delete S3 object {key}: {e}")
        return False
