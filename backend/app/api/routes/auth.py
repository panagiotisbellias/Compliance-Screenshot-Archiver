"""Authentication endpoints for login and token management."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    """Login request model."""

    email: str
    password: str


class LoginResponse(BaseModel):
    """Login response model."""

    token: str
    user: dict[str, Any]


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """
    Authenticate user and return JWT token.

    For development, this provides mock authentication.
    In production, this would integrate with AWS Cognito.

    Args:
        request: Login credentials

    Returns:
        LoginResponse: JWT token and user info

    Raises:
        HTTPException: If authentication fails
    """
    # Development mock - accept demo credentials
    if request.email == "admin@example.com" and request.password == "password":
        # Mock JWT token for development
        mock_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbi0xMjMiLCJlbWFpbCI6ImFkbWluQGV4YW1wbGUuY29tIiwicm9sZSI6ImFkbWluIiwiY29nbml0bzpncm91cHMiOlsiYWRtaW4iXSwiZXhwIjo5OTk5OTk5OTk5fQ.development-mock-signature"

        return LoginResponse(
            token=mock_token,
            user={"id": "admin-123", "email": "admin@example.com", "role": "admin"},
        )

    # For production, integrate with AWS Cognito here
    # This would involve:
    # 1. Validate credentials with Cognito
    # 2. Get JWT tokens from Cognito
    # 3. Return the tokens and user info

    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/logout")
async def logout() -> dict[str, str]:
    """
    Logout the current user.

    Returns:
        dict: Success message
    """
    # In production, this would invalidate the token in Cognito
    return {"message": "Logged out successfully"}
