from __future__ import annotations

import logging
import time
from typing import Any, cast

import httpx
from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError

from ..core.config import settings

logger = logging.getLogger(__name__)

# Role hierarchy: admin > operator > viewer
ROLE_HIERARCHY = {
    "viewer": 1,
    "operator": 2,
    "admin": 3,
}

# Cognito group to role mapping
COGNITO_GROUP_TO_ROLE = {
    "admin": "admin",
    "user": "operator",  # Regular users can trigger captures
    "auditor": "viewer",  # Auditors have read-only access
}


class AuthenticationError(HTTPException):
    """Custom authentication error."""

    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(status_code=401, detail=detail)


class AuthorizationError(HTTPException):
    """Custom authorization error."""

    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(status_code=403, detail=detail)


# Simple JWKS cache with TTL
_jwks_cache: dict[str, Any] = {"data": None, "expires_at": 0.0}
_JWKS_CACHE_TTL = 300  # 5 minutes


async def get_jwks() -> dict[str, Any]:
    """
    Fetch and cache JWKS from Cognito with TTL.

    Returns:
        dict: JWKS data from Cognito.

    Raises:
        AuthenticationError: If JWKS cannot be fetched.
    """
    if not settings.jwt_jwks_url:
        raise AuthenticationError("JWKS URL not configured")

    current_time = time.time()

    # Return cached JWKS if still valid
    if _jwks_cache["data"] is not None and current_time < _jwks_cache["expires_at"]:
        return dict(_jwks_cache["data"])  # Explicit cast to satisfy mypy

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(str(settings.jwt_jwks_url))
            response.raise_for_status()
            jwks_data: dict[str, Any] = response.json()

            # Cache the result
            _jwks_cache["data"] = jwks_data
            _jwks_cache["expires_at"] = current_time + _JWKS_CACHE_TTL

            return jwks_data
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        raise AuthenticationError("Failed to validate token") from e


def _find_signing_key(jwks: dict[str, Any], key_id: str) -> dict[str, Any]:
    """Find the signing key with the given key ID from JWKS."""
    for key in jwks.get("keys", []):
        if key.get("kid") == key_id:
            return dict(key)  # Explicit cast to satisfy mypy
    raise AuthenticationError("Unable to find signing key")


def _determine_user_role(cognito_groups: list[str]) -> str:
    """Determine user role from Cognito groups based on hierarchy."""
    user_role = "viewer"  # Default role
    for group in cognito_groups:
        if group in COGNITO_GROUP_TO_ROLE:
            group_role = COGNITO_GROUP_TO_ROLE[group]
            if ROLE_HIERARCHY[group_role] > ROLE_HIERARCHY[user_role]:
                user_role = group_role
    return user_role


def _validate_token_header(token: str) -> str:
    """Validate token header and extract key ID."""
    unverified_header = jwt.get_unverified_header(token)
    key_id = unverified_header.get("kid")
    if not key_id:
        raise AuthenticationError("Token missing key ID")
    return str(key_id)  # Explicit cast to satisfy mypy


def _decode_jwt_claims(token: str, signing_key: dict[str, Any]) -> dict[str, Any]:
    """Decode and validate JWT claims."""
    return cast(
        dict[str, Any],
        jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.jwt_audience or settings.cognito_client_id,
            issuer=settings.jwt_issuer
            or f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}",
        ),
    )


async def verify_jwt_token(token: str) -> dict[str, Any]:
    """
    Verify JWT token and extract claims.

    Args:
        token: JWT token to verify.

    Returns:
        dict: Token claims including user info.

    Raises:
        AuthenticationError: If token is invalid or expired.
    """
    try:
        # Get JWKS for token verification
        jwks = await get_jwks()

        # Get and validate the signing key
        key_id = _validate_token_header(token)
        signing_key = _find_signing_key(jwks, key_id)

        # Verify the token and decode claims
        claims = _decode_jwt_claims(token, signing_key)

        # Extract user information
        user_id = claims.get("sub")
        if not user_id:
            raise AuthenticationError("Token missing user ID")

        email = claims.get("email")
        cognito_groups = claims.get("cognito:groups", [])
        user_role = _determine_user_role(cognito_groups)

        return {
            "sub": user_id,
            "email": email or "",
            "role": user_role,
            "cognito_groups": cognito_groups,
        }

    except ExpiredSignatureError:
        raise AuthenticationError("Token has expired") from None
    except JWTClaimsError as e:
        raise AuthenticationError(f"Token claims invalid: {e}") from e
    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise AuthenticationError("Invalid token") from e
    except AuthenticationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during token validation: {e}")
        raise AuthenticationError("Authentication failed") from e


async def get_current_user(request: Request) -> dict[str, Any]:
    """
    Extract and validate JWT token from Authorization header.

    Args:
        request: FastAPI request object.

    Returns:
        dict: User information from JWT claims.

    Raises:
        AuthenticationError: If authentication fails.
    """
    from ..core.config import settings

    authorization = request.headers.get("Authorization")

    if not authorization:
        raise AuthenticationError("Authorization header missing")

    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise AuthenticationError("Invalid authorization scheme")
    except ValueError:
        raise AuthenticationError("Invalid authorization header format") from None

    # Development mode - accept the mock token
    if settings.env == "dev" and token.startswith(
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbi0xMjMi"
    ):
        return {
            "sub": "admin-123",
            "email": "admin@example.com",
            "role": "admin",
            "cognito_groups": ["admin"],
        }

    return await verify_jwt_token(token)


# Pre-built dependencies for common roles to avoid B008 issues
async def require_viewer(user_info: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Require viewer role or higher."""
    user_role = user_info.get("role", "viewer")
    if ROLE_HIERARCHY[user_role] < ROLE_HIERARCHY["viewer"]:
        raise AuthorizationError(f"Role 'viewer' required, but user has role '{user_role}'")
    return user_info


async def require_operator(user_info: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Require operator role or higher."""
    user_role = user_info.get("role", "viewer")
    if ROLE_HIERARCHY[user_role] < ROLE_HIERARCHY["operator"]:
        raise AuthorizationError(f"Role 'operator' required, but user has role '{user_role}'")
    return user_info


async def require_admin(user_info: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Require admin role."""
    user_role = user_info.get("role", "viewer")
    if ROLE_HIERARCHY[user_role] < ROLE_HIERARCHY["admin"]:
        raise AuthorizationError(f"Role 'admin' required, but user has role '{user_role}'")
    return user_info


# Utility function to check if user has admin privileges
def is_admin(user_info: dict[str, Any]) -> bool:
    """
    Check if user has admin privileges.

    Args:
        user_info: User information from JWT claims.

    Returns:
        bool: True if user is admin.
    """
    return user_info.get("role") == "admin"


# Utility function to check if user can access resource
def can_access_user_resource(user_info: dict[str, Any], resource_user_id: str) -> bool:
    """
    Check if user can access a resource belonging to another user.

    Args:
        user_info: User information from JWT claims.
        resource_user_id: User ID of the resource owner.

    Returns:
        bool: True if user can access the resource.
    """
    # Admins can access any resource
    if is_admin(user_info):
        return True

    # Users can only access their own resources
    return user_info.get("sub") == resource_user_id
