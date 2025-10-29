"""Test configuration and fixtures."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import boto3
import pytest
from moto import mock_aws

# Set test environment
os.environ["APP_ENV"] = "test"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["S3_BUCKET_ARTIFACTS"] = "test-artifacts-bucket"
os.environ["KMS_KEY_ARN"] = "arn:aws:kms:us-east-1:123456789012:key/test-key"
os.environ["DDB_TABLE_SCHEDULES"] = "test-schedules"
os.environ["DDB_TABLE_CAPTURES"] = "test-captures"


@pytest.fixture
def mock_aws_credentials() -> None:
    """Mock AWS credentials to prevent accidental real AWS calls."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"


@pytest.fixture
def mock_s3_bucket(mock_aws_credentials: None) -> Generator[str, None, None]:
    """Create a mock S3 bucket for testing."""
    with mock_aws():
        s3_client = boto3.client("s3", region_name="us-east-1")
        bucket_name = "test-artifacts-bucket"

        # Create bucket with versioning and Object Lock
        s3_client.create_bucket(Bucket=bucket_name)
        s3_client.put_bucket_versioning(
            Bucket=bucket_name, VersioningConfiguration={"Status": "Enabled"}
        )

        yield bucket_name


@pytest.fixture
def mock_dynamodb_tables(mock_aws_credentials: None) -> Generator[dict[str, Any], None, None]:
    """Create mock DynamoDB tables for testing."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        # Create schedules table
        schedules_table = dynamodb.create_table(
            TableName="test-schedules",
            KeySchema=[{"AttributeName": "schedule_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "schedule_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "next_capture_time", "AttributeType": "N"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "UserSchedulesIndex",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "next_capture_time", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "NextCaptureIndex",
                    "KeySchema": [{"AttributeName": "next_capture_time", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Create captures table
        captures_table = dynamodb.create_table(
            TableName="test-captures",
            KeySchema=[
                {"AttributeName": "capture_id", "KeyType": "HASH"},
                {"AttributeName": "created_at", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "capture_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "N"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "url", "AttributeType": "S"},
                {"AttributeName": "sha256", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "UserCapturesIndex",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "UrlCapturesIndex",
                    "KeySchema": [
                        {"AttributeName": "url", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "HashIndex",
                    "KeySchema": [{"AttributeName": "sha256", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield {
            "schedules": schedules_table,
            "captures": captures_table,
        }


@pytest.fixture
def mock_playwright() -> Generator[dict[str, Any], None, None]:
    """Mock Playwright for testing without launching actual browser."""
    with patch("app.capture_engine.engine.async_playwright") as mock:
        # Setup mock browser behavior
        mock_page = MagicMock()
        mock_page.pdf = AsyncMock(return_value=b"fake_pdf_content")
        mock_page.screenshot = AsyncMock(return_value=b"fake_png_content")
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        # Create an async context manager
        async def aenter(self):
            return mock_playwright_instance

        async def aexit(self, *args):
            return None

        mock.return_value.__aenter__ = aenter
        mock.return_value.__aexit__ = aexit

        # Return access to mock objects for assertions
        yield {
            "mock": mock,
            "playwright_instance": mock_playwright_instance,
            "browser": mock_browser,
            "context": mock_context,
            "page": mock_page,
        }


@pytest.fixture
def sample_capture_data() -> dict[str, Any]:
    """Sample capture data for testing."""
    return {
        "capture_id": "test-capture-123",
        "url": "https://example.com",
        "artifact_type": "pdf",
        "user_id": "test-user",
        "sha256": "abcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234",
        "s3_key": "captures/test-capture-123.pdf",
        "metadata": {"test": "value"},
    }


@pytest.fixture
def mock_user_auth() -> dict[str, str]:
    """Mock user authentication data."""
    return {
        "sub": "test-user-123",
        "email": "test@example.com",
        "role": "operator",
    }
