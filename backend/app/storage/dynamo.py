from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from app.core.config import settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class CaptureData:
    """Data for creating a capture record."""

    capture_id: str
    url: str
    sha256: str
    s3_key: str
    artifact_type: str
    user_id: str
    metadata: Optional[dict[str, Any]] = None


@dataclass
class ScheduleData:
    """Data for creating a schedule record."""

    schedule_id: str
    user_id: str
    url: str
    cron_expression: str
    artifact_type: str = "pdf"
    enabled: bool = True
    metadata: Optional[dict[str, Any]] = None


def ddb() -> Any:
    """
    DynamoDB resource.

    Returns:
        boto3.resources.factory.dynamodb.ServiceResource: DDB resource.
    """
    return boto3.resource("dynamodb", region_name=settings.aws_region)


def table(name: str) -> Any:
    """
    Get a DynamoDB table handle.

    Args:
        name: Table name.

    Returns:
        mypy_boto3_dynamodb.service_resource.Table: Table handle.
    """
    return ddb().Table(name)


# Capture Operations
def create_capture(data: Optional[CaptureData] = None, **kwargs) -> dict[str, Any]:
    """
    Create a capture record in DynamoDB.

    Args:
        data: Capture data containing all required fields (preferred).
        **kwargs: Individual fields for backward compatibility.

    Returns:
        dict: The created capture record.
    """
    # Handle backward compatibility
    if data is None:
        data = CaptureData(
            capture_id=kwargs["capture_id"],
            url=kwargs["url"],
            sha256=kwargs["sha256"],
            s3_key=kwargs["s3_key"],
            artifact_type=kwargs["artifact_type"],
            user_id=kwargs["user_id"],
            metadata=kwargs.get("metadata"),
        )

    captures_table = table(settings.ddb_table_captures)

    timestamp = Decimal(str(time.time()))

    item = {
        "capture_id": data.capture_id,
        "created_at": timestamp,
        "url": data.url,
        "sha256": data.sha256,
        "s3_key": data.s3_key,
        "artifact_type": data.artifact_type,
        "user_id": data.user_id,
        "status": "completed",
        "metadata": data.metadata or {},
    }

    try:
        captures_table.put_item(Item=item)
        logger.info(f"Created capture record: {data.capture_id}")
        return item
    except ClientError as e:
        logger.error(f"Failed to create capture record: {e}")
        raise


def get_capture(capture_id: str):
    """
    Get a capture record by ID.

    Args:
        capture_id: Capture ID.

    Returns:
        dict or None: Capture record or None if not found.
    """
    captures_table = table(settings.ddb_table_captures)

    try:
        response = captures_table.query(KeyConditionExpression=Key("capture_id").eq(capture_id))
        items = response.get("Items", [])
        return items[0] if items else None
    except ClientError as e:
        logger.error(f"Failed to get capture: {e}")
        return None


def list_captures_by_user(
    user_id: str,
    limit: int = 50,
    last_evaluated_key: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    List captures for a specific user.

    Args:
        user_id: User ID.
        limit: Maximum number of items to return.
        last_evaluated_key: Pagination token.

    Returns:
        dict: List of captures with pagination info.
    """
    captures_table = table(settings.ddb_table_captures)

    query_params = {
        "IndexName": "UserCapturesIndex",
        "KeyConditionExpression": Key("user_id").eq(user_id),
        "ScanIndexForward": False,  # Most recent first
        "Limit": limit,
    }

    if last_evaluated_key:
        query_params["ExclusiveStartKey"] = last_evaluated_key

    try:
        response = captures_table.query(**query_params)
        return {
            "items": response.get("Items", []),
            "last_evaluated_key": response.get("LastEvaluatedKey"),
            "count": response.get("Count", 0),
        }
    except ClientError as e:
        logger.error(f"Failed to list captures: {e}")
        return {"items": [], "last_evaluated_key": None, "count": 0}


def get_capture_by_hash(sha256: str):
    """
    Find a capture by its SHA-256 hash.

    Args:
        sha256: SHA-256 hash.

    Returns:
        dict | None: Capture record or None if not found.
    """
    captures_table = table(settings.ddb_table_captures)

    try:
        response = captures_table.query(
            IndexName="HashIndex",
            KeyConditionExpression=Key("sha256").eq(sha256),
            Limit=1,
        )
        items = response.get("Items", [])
        return items[0] if items else None
    except ClientError as e:
        logger.error(f"Failed to get capture by hash: {e}")
        return None


# Schedule Operations
def create_schedule(data: Optional[ScheduleData] = None, **kwargs) -> dict[str, Any]:
    """
    Create a schedule record in DynamoDB.

    Args:
        data: Schedule data containing all required fields (preferred).
        **kwargs: Individual fields for backward compatibility.

    Returns:
        dict: The created schedule record.
    """
    # Handle backward compatibility
    if data is None:
        data = ScheduleData(
            schedule_id=kwargs["schedule_id"],
            user_id=kwargs["user_id"],
            url=kwargs["url"],
            cron_expression=kwargs["cron_expression"],
            artifact_type=kwargs.get("artifact_type", "pdf"),
            enabled=kwargs.get("enabled", True),
            metadata=kwargs.get("metadata"),
        )

    schedules_table = table(settings.ddb_table_schedules)

    timestamp = Decimal(str(time.time()))

    item = {
        "schedule_id": data.schedule_id,
        "user_id": data.user_id,
        "url": data.url,
        "cron_expression": data.cron_expression,
        "artifact_type": data.artifact_type,
        "enabled": data.enabled,
        "created_at": timestamp,
        "updated_at": timestamp,
        "next_capture_time": timestamp,  # Will be updated by scheduler
        "metadata": data.metadata or {},
    }

    try:
        schedules_table.put_item(Item=item)
        logger.info(f"Created schedule: {data.schedule_id}")
        return item
    except ClientError as e:
        logger.error(f"Failed to create schedule: {e}")
        raise


def get_schedule(schedule_id: str):
    """
    Get a schedule record by ID.

    Args:
        schedule_id: Schedule ID.

    Returns:
        dict | None: Schedule record or None if not found.
    """
    schedules_table = table(settings.ddb_table_schedules)

    try:
        response = schedules_table.get_item(Key={"schedule_id": schedule_id})
        item = response.get("Item")
        return item
    except ClientError as e:
        logger.error(f"Failed to get schedule: {e}")
        return None


def list_schedules_by_user(
    user_id: str,
    limit: int = 50,
    last_evaluated_key: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    List schedules for a specific user.

    Args:
        user_id: User ID.
        limit: Maximum number of items to return.
        last_evaluated_key: Pagination token.

    Returns:
        dict: List of schedules with pagination info.
    """
    schedules_table = table(settings.ddb_table_schedules)

    query_params = {
        "IndexName": "UserSchedulesIndex",
        "KeyConditionExpression": Key("user_id").eq(user_id),
        "Limit": limit,
    }

    if last_evaluated_key:
        query_params["ExclusiveStartKey"] = last_evaluated_key

    try:
        response = schedules_table.query(**query_params)
        return {
            "items": response.get("Items", []),
            "last_evaluated_key": response.get("LastEvaluatedKey"),
            "count": response.get("Count", 0),
        }
    except ClientError as e:
        logger.error(f"Failed to list schedules: {e}")
        return {"items": [], "last_evaluated_key": None, "count": 0}


def update_schedule(
    schedule_id: str,
    updates: dict[str, Any],
):
    """
    Update a schedule record.

    Args:
        schedule_id: Schedule ID.
        updates: Fields to update.

    Returns:
        dict | None: Updated schedule record or None if failed.
    """
    schedules_table = table(settings.ddb_table_schedules)

    # DynamoDB reserved keywords that need attribute name mapping
    reserved_keywords = {
        "url",
        "name",
        "timestamp",
        "data",
        "status",
        "user",
        "role",
        "group",
        "type",
        "size",
        "hash",
    }

    # Build update expression with attribute name mapping for reserved keywords
    update_expr = "SET updated_at = :updated_at"
    expr_values = {":updated_at": Decimal(str(time.time()))}
    expr_attr_names = {}

    for key, value in updates.items():
        if key not in ["schedule_id", "created_at"]:  # Don't update keys
            if key in reserved_keywords:
                # Use attribute name mapping for reserved keywords
                attr_name = f"#{key}"
                update_expr += f", {attr_name} = :{key}"
                expr_attr_names[attr_name] = key
            else:
                update_expr += f", {key} = :{key}"
            expr_values[f":{key}"] = value

    update_params = {
        "Key": {"schedule_id": schedule_id},
        "UpdateExpression": update_expr,
        "ExpressionAttributeValues": expr_values,
        "ReturnValues": "ALL_NEW",
    }

    # Only add ExpressionAttributeNames if we have reserved keywords
    if expr_attr_names:
        update_params["ExpressionAttributeNames"] = expr_attr_names

    try:
        response = schedules_table.update_item(**update_params)
        logger.info(f"Updated schedule: {schedule_id}")
        attrs = response.get("Attributes")
        return attrs
    except ClientError as e:
        logger.error(f"Failed to update schedule: {e}")
        return None


def delete_schedule(schedule_id: str) -> bool:
    """
    Delete a schedule record.

    Args:
        schedule_id: Schedule ID.

    Returns:
        bool: True if deleted, False otherwise.
    """
    schedules_table = table(settings.ddb_table_schedules)

    try:
        schedules_table.delete_item(Key={"schedule_id": schedule_id})
        logger.info(f"Deleted schedule: {schedule_id}")
        return True
    except ClientError as e:
        logger.error(f"Failed to delete schedule: {e}")
        return False


def delete_capture(capture_id: str, created_at: Optional[float] = None) -> bool:
    """
    Delete a capture record.

    Args:
        capture_id: Capture ID.
        created_at: Creation timestamp (required for composite key).

    Returns:
        bool: True if deleted, False otherwise.
    """
    captures_table = table(settings.ddb_table_captures)

    try:
        # If created_at not provided, get it from the capture first
        if created_at is None:
            capture_data = get_capture(capture_id)
            if not capture_data:
                logger.error(f"Capture {capture_id} not found for deletion")
                return False
            created_at = float(capture_data["created_at"])

        # Use composite key for deletion
        key = {"capture_id": capture_id, "created_at": Decimal(str(created_at))}

        captures_table.delete_item(Key=key)
        logger.info(f"Deleted capture: {capture_id}")
        return True
    except ClientError as e:
        logger.error(f"Failed to delete capture: {e}")
        return False
