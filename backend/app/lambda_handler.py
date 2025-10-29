from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mangum import Mangum  # type: ignore

from .capture_engine.processor import process_capture_request

# Import moved to inside eventbridge_handler to avoid importing capture dependencies in API Lambda
from .core.logging import jlog
from .main import app

logger = logging.getLogger(__name__)


# Initialize Mangum handler for AWS Lambda
def create_handler():
    """Create the Lambda handler with lazy import to avoid circular imports."""
    return Mangum(app)


# Initialize the handler for FastAPI Lambda
handler = create_handler()


# For direct Lambda invocation (API Gateway)
def lambda_handler(event, context):
    """Main Lambda handler for API Gateway integration."""
    return handler(event, context)


def eventbridge_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """
    Entry point for EventBridge/SQS-triggered Lambdas (scheduling/worker).

    Args:
        event: AWS event payload (EventBridge or SQS batch).
        _context: Lambda context.

    Returns:
        dict: Result summary.
    """
    jlog(logger, "eventbridge_event_received", event_detail=event.get("detail", {}))

    try:
        # Handle EventBridge scheduled events
        if event.get("source") == "aws.scheduler":
            return handle_scheduled_capture(event)

        # Handle SQS batch events
        elif "Records" in event:
            return handle_sqs_batch(event)

        # Handle direct invocation with capture details
        elif "url" in event:
            return handle_direct_capture(event)

        else:
            jlog(logger, "unknown_event_type", event_keys=list(event.keys()), level="WARNING")
            return {"status": "ignored", "reason": "unknown_event_type"}

    except Exception as e:
        jlog(logger, "eventbridge_handler_error", error=str(e), level="ERROR")
        return {"status": "error", "error": str(e)}


def handle_scheduled_capture(event: dict[str, Any]) -> dict[str, Any]:
    """Handle EventBridge Scheduler triggered captures."""

    detail = event.get("detail", {})
    url = detail.get("url")
    artifact_type = detail.get("artifact_type", "pdf")
    user_id = detail.get("user_id", "scheduler")
    schedule_id = detail.get("schedule_id")

    if not url:
        return {"status": "error", "error": "No URL provided in event detail"}

    # Run the async capture process
    result = asyncio.run(
        process_capture_request(
            url=url,
            artifact_type=artifact_type,
            user_id=user_id,
            metadata={"schedule_id": schedule_id} if schedule_id else None,
        )
    )

    return {"status": "processed", "capture_result": result}


def handle_sqs_batch(event: dict[str, Any]) -> dict[str, Any]:
    """Handle SQS batch of capture requests."""

    records = event.get("Records", [])
    results = []

    for record in records:
        try:
            # Parse SQS message body
            body = json.loads(record.get("body", "{}"))
            url = body.get("url")
            artifact_type = body.get("artifact_type", "pdf")
            user_id = body.get("user_id", "sqs")
            metadata = body.get("metadata", {})

            if not url:
                results.append({"status": "error", "error": "No URL in SQS message"})
                continue

            # Process the capture
            result = asyncio.run(
                process_capture_request(
                    url=url,
                    artifact_type=artifact_type,
                    user_id=user_id,
                    metadata=metadata,
                )
            )
            results.append(result)

        except Exception as e:
            jlog(logger, "sqs_record_error", error=str(e), level="ERROR")
            results.append({"status": "error", "error": str(e)})

    return {"status": "batch_processed", "results": results}


def handle_direct_capture(event: dict[str, Any]) -> dict[str, Any]:
    """Handle direct Lambda invocation with capture details."""

    url = event.get("url")
    artifact_type = event.get("artifact_type", "pdf")
    user_id = event.get("user_id", "direct")
    metadata = event.get("metadata", {})

    if not url:
        return {"status": "error", "error": "No URL provided"}

    result = asyncio.run(
        process_capture_request(
            url=url,
            artifact_type=artifact_type,
            user_id=user_id,
            metadata=metadata,
        )
    )

    return {"status": "processed", "capture_result": result}
