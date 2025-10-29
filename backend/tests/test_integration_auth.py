"""Integration tests for authentication in API routes."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth.deps import AuthenticationError
from app.main import app


class TestAuthenticationIntegration:
    """Test authentication integration with API routes."""

    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)

    def test_health_endpoint_no_auth_required(self):
        """Test that health endpoint doesn't require authentication."""
        response = self.client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "auth" in data

    def test_auth_config_no_auth_required(self):
        """Test that auth config endpoint doesn't require authentication."""
        response = self.client.get("/api/auth/config")
        assert response.status_code == 200
        data = response.json()
        assert "cognito" in data
        assert "roles" in data
        assert data["roles"]["available"] == ["viewer", "operator", "admin"]

    def test_protected_endpoint_no_token(self):
        """Test that protected endpoints require authentication."""
        response = self.client.get("/api/captures")
        assert response.status_code == 401
        assert "Authorization header missing" in response.json()["detail"]

    def test_protected_endpoint_invalid_token(self):
        """Test that protected endpoints reject invalid tokens."""
        headers = {"Authorization": "Bearer invalid-token"}

        with patch("app.auth.deps.verify_jwt_token") as mock_verify:
            mock_verify.side_effect = AuthenticationError("Invalid token")

            response = self.client.get("/api/captures", headers=headers)
            assert response.status_code == 401

    def test_protected_endpoint_insufficient_role(self):
        """Test that endpoints check role requirements."""
        headers = {"Authorization": "Bearer valid-token"}

        # Mock a viewer user trying to access operator endpoint
        with patch("app.auth.deps.verify_jwt_token") as mock_verify:
            mock_verify.return_value = {
                "sub": "user-123",
                "email": "viewer@example.com",
                "role": "viewer",
                "cognito_groups": ["auditor"],
            }

            response = self.client.post(
                "/api/captures/trigger?url=https://example.com", headers=headers
            )
            assert response.status_code == 403
            assert "Role 'operator' required" in response.json()["detail"]

    @patch("app.api.routes.captures.list_captures_by_user")
    @patch("app.auth.deps.verify_jwt_token")
    def test_successful_authenticated_request(self, mock_verify, mock_list_captures):
        """Test successful authenticated request."""
        # Mock authentication
        mock_verify.return_value = {
            "sub": "user-123",
            "email": "user@example.com",
            "role": "viewer",
            "cognito_groups": ["auditor"],
        }

        # Mock database response
        mock_list_captures.return_value = {"items": []}

        headers = {"Authorization": "Bearer valid-token"}
        response = self.client.get("/api/captures", headers=headers)

        assert response.status_code == 200
        assert response.json() == []

        # Verify user ID was passed to database query
        mock_list_captures.assert_called_once()
        call_args = mock_list_captures.call_args
        assert call_args[1]["user_id"] == "user-123"

    @patch("app.auth.deps.verify_jwt_token")
    def test_auth_status_endpoint(self, mock_verify):
        """Test authentication status endpoint."""
        # Mock authentication
        mock_verify.return_value = {
            "sub": "user-123",
            "email": "operator@example.com",
            "role": "operator",
            "cognito_groups": ["user"],
        }

        headers = {"Authorization": "Bearer valid-token"}
        response = self.client.get("/api/auth/status", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["user_id"] == "user-123"
        assert data["role"] == "operator"
        assert data["permissions"]["can_view"] is True
        assert data["permissions"]["can_trigger_captures"] is True
        assert data["permissions"]["can_admin"] is False

    def test_invalid_authorization_scheme(self):
        """Test invalid authorization scheme."""
        headers = {"Authorization": "Basic invalid-token"}
        response = self.client.get("/api/captures", headers=headers)
        assert response.status_code == 401
        assert "Invalid authorization scheme" in response.json()["detail"]

    def test_malformed_authorization_header(self):
        """Test malformed authorization header."""
        headers = {"Authorization": "Bearer"}
        response = self.client.get("/api/captures", headers=headers)
        assert response.status_code == 401
        assert "Invalid authorization header format" in response.json()["detail"]
