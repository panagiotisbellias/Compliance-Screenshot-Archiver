"""Minimal API Lambda handler without capture engine dependencies."""

from __future__ import annotations

import logging

from mangum import Mangum  # type: ignore

from .core.logging import configure_logging
from .main import app

# Configure logging
configure_logging(logging.INFO)
logger = logging.getLogger(__name__)


def create_api_handler():
    """Create the Lambda handler with lazy import to avoid circular imports."""
    return Mangum(app)


# Initialize the handler for FastAPI Lambda (API Gateway only)
api_handler = create_api_handler()


def lambda_handler(event, context):
    """API Lambda handler for API Gateway integration only."""
    return api_handler(event, context)
