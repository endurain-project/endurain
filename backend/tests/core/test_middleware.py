"""
Tests for CSRF middleware implementation (Phase B.16).

Verifies:
1. Middleware only requires X-CSRF-Token header (not cookie)
2. In-memory token validation works correctly
3. Web clients are enforced, mobile clients are exempt
4. Exempt paths work correctly
5. Only POST/PUT/DELETE/PATCH methods are checked
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.middleware import CSRFMiddleware


@pytest.fixture
def app_with_csrf():
    """
    Creates a minimal FastAPI app with CSRF middleware for testing.

    Returns:
        FastAPI: A test app with CSRF middleware and test endpoints.
    """
    app = FastAPI()

    # Add CSRF middleware
    app.add_middleware(CSRFMiddleware)

    # Test endpoints
    @app.get("/api/v1/test/get")
    async def test_get():
        return {"message": "GET success"}

    @app.post("/api/v1/test/post")
    async def test_post():
        return {"message": "POST success"}

    @app.put("/api/v1/test/put")
    async def test_put():
        return {"message": "PUT success"}

    @app.delete("/api/v1/test/delete")
    async def test_delete():
        return {"message": "DELETE success"}

    @app.patch("/api/v1/test/patch")
    async def test_patch():
        return {"message": "PATCH success"}

    # Exempt endpoint for testing
    @app.post("/api/v1/auth/login")
    async def test_login():
        return {"message": "Login success"}

    # Public endpoint for testing
    @app.post("/api/v1/public/idp/session/test/callback")
    async def test_public():
        return {"message": "Public success"}

    return app


@pytest.fixture
def client(app_with_csrf):
    """
    Creates a TestClient for the app with CSRF middleware.

    Args:
        app_with_csrf: The FastAPI app fixture with CSRF middleware.

    Returns:
        TestClient: A test client for making requests.
    """
    return TestClient(app_with_csrf)


class TestCSRFMiddlewareWebClients:
    """
    Tests for CSRF middleware behavior with web clients (X-Client-Type: web).
    """

    def test_get_request_no_csrf_required(self, client):
        """
        Test that GET requests from web clients don't require CSRF token.

        Verifies:
            - GET requests succeed without X-CSRF-Token header
            - Only state-changing methods require CSRF
        """
        response = client.get(
            "/api/v1/test/get",
            headers={"X-Client-Type": "web"}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "GET success"}

    def test_post_without_csrf_forbidden(self, client):
        """
        Test that POST requests from web clients require CSRF token.

        Verifies:
            - POST without X-CSRF-Token header returns 403
            - Error message indicates CSRF token is required
        """
        with pytest.raises(Exception) as exc_info:
            client.post(
                "/api/v1/test/post",
                headers={"X-Client-Type": "web"}
            )
        assert "403" in str(exc_info.value)
        assert "CSRF token required" in str(exc_info.value)

    def test_post_with_csrf_success(self, client):
        """
        Test that POST requests with CSRF token succeed.

        Verifies:
            - X-CSRF-Token header is accepted (header-only, no cookie required)
            - In-memory token model works correctly
        """
        response = client.post(
            "/api/v1/test/post",
            headers={
                "X-Client-Type": "web",
                "X-CSRF-Token": "test-csrf-token-123"
            }
        )
        assert response.status_code == 200
        assert response.json() == {"message": "POST success"}

    def test_put_with_csrf_success(self, client):
        """
        Test that PUT requests with CSRF token succeed.

        Verifies:
            - PUT method is checked for CSRF
            - X-CSRF-Token header works
        """
        response = client.put(
            "/api/v1/test/put",
            headers={
                "X-Client-Type": "web",
                "X-CSRF-Token": "test-csrf-token-123"
            }
        )
        assert response.status_code == 200
        assert response.json() == {"message": "PUT success"}

    def test_delete_with_csrf_success(self, client):
        """
        Test that DELETE requests with CSRF token succeed.

        Verifies:
            - DELETE method is checked for CSRF
            - X-CSRF-Token header works
        """
        response = client.delete(
            "/api/v1/test/delete",
            headers={
                "X-Client-Type": "web",
                "X-CSRF-Token": "test-csrf-token-123"
            }
        )
        assert response.status_code == 200
        assert response.json() == {"message": "DELETE success"}

    def test_patch_with_csrf_success(self, client):
        """
        Test that PATCH requests with CSRF token succeed.

        Verifies:
            - PATCH method is checked for CSRF
            - X-CSRF-Token header works
        """
        response = client.patch(
            "/api/v1/test/patch",
            headers={
                "X-Client-Type": "web",
                "X-CSRF-Token": "test-csrf-token-123"
            }
        )
        assert response.status_code == 200
        assert response.json() == {"message": "PATCH success"}


class TestCSRFMiddlewareMobileClients:
    """
    Tests for CSRF middleware behavior with mobile clients (no X-Client-Type or non-web).
    """

    def test_post_without_client_type_success(self, client):
        """
        Test that POST requests without X-Client-Type header succeed.

        Verifies:
            - Mobile clients (no X-Client-Type) are exempt from CSRF
            - No X-CSRF-Token required for non-web clients
        """
        response = client.post("/api/v1/test/post")
        assert response.status_code == 200
        assert response.json() == {"message": "POST success"}

    def test_post_with_mobile_client_type_success(self, client):
        """
        Test that POST requests from mobile clients succeed without CSRF.

        Verifies:
            - X-Client-Type: mobile is exempt from CSRF checks
            - No X-CSRF-Token required
        """
        response = client.post(
            "/api/v1/test/post",
            headers={"X-Client-Type": "mobile"}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "POST success"}

    def test_delete_with_app_client_type_success(self, client):
        """
        Test that DELETE requests from app clients succeed without CSRF.

        Verifies:
            - Any non-"web" X-Client-Type is exempt from CSRF
            - DELETE works without X-CSRF-Token for mobile/app clients
        """
        response = client.delete(
            "/api/v1/test/delete",
            headers={"X-Client-Type": "app"}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "DELETE success"}


class TestCSRFMiddlewareExemptPaths:
    """
    Tests for CSRF middleware exempt paths (authentication endpoints, public routes).
    """

    def test_login_exempt_no_csrf_required(self, client):
        """
        Test that /api/v1/auth/login is exempt from CSRF checks.

        Verifies:
            - Login endpoint works without X-CSRF-Token
            - Even with X-Client-Type: web
        """
        response = client.post(
            "/api/v1/auth/login",
            headers={"X-Client-Type": "web"}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "Login success"}

    def test_public_idp_route_exempt(self, client):
        """
        Test that public IdP routes are exempt from CSRF checks.

        Verifies:
            - Routes starting with /api/v1/public/idp/session/ are exempt
            - Dynamic route segments work correctly
        """
        response = client.post(
            "/api/v1/public/idp/session/test/callback",
            headers={"X-Client-Type": "web"}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "Public success"}


class TestCSRFMiddlewareInMemoryModel:
    """
    Tests for CSRF middleware in-memory token model (B.16).

    Verifies that middleware only checks for header presence,
    not cookie-based CSRF tokens (OAuth 2.1 compliance).
    """

    def test_csrf_header_only_no_cookie_required(self, client):
        """
        Test that CSRF token is accepted from header without cookie.

        Verifies:
            - Middleware only requires X-CSRF-Token header
            - No CSRF cookie is checked or required
            - In-memory token storage model is supported
        """
        # Request with CSRF header but no CSRF cookie
        response = client.post(
            "/api/v1/test/post",
            headers={
                "X-Client-Type": "web",
                "X-CSRF-Token": "in-memory-csrf-token-abc123"
            }
        )
        assert response.status_code == 200
        assert response.json() == {"message": "POST success"}

    def test_csrf_token_any_format_accepted_by_middleware(self, client):
        """
        Test that middleware accepts any CSRF token format in header.

        Verifies:
            - Middleware only checks for header presence (not format)
            - Cryptographic validation happens in route handler
            - This separation of concerns is intentional
        """
        # Various token formats should pass middleware check
        token_formats = [
            "simple-token",
            "base64url-encoded-token",
            "a" * 64,  # Long token
            "123",     # Short token
        ]

        for token in token_formats:
            response = client.post(
                "/api/v1/test/post",
                headers={
                    "X-Client-Type": "web",
                    "X-CSRF-Token": token
                }
            )
            assert response.status_code == 200, f"Failed for token format: {token}"


class TestCSRFMiddlewareSameSiteCookie:
    """
    Tests for SameSite=Strict cookie behavior (B.16).

    Note: These tests verify that CSRF middleware doesn't rely on cookies.
    The actual SameSite=Strict enforcement is at the browser level for the
    refresh token cookie, which is tested via integration tests.
    """

    def test_csrf_works_without_cookies(self, client):
        """
        Test that CSRF protection works without any cookies.

        Verifies:
            - CSRF middleware doesn't check cookies
            - Only X-CSRF-Token header is required
            - OAuth 2.1 in-memory token model is followed
        """
        # Request without any cookies, only CSRF header
        response = client.post(
            "/api/v1/test/post",
            headers={
                "X-Client-Type": "web",
                "X-CSRF-Token": "header-only-token"
            },
            cookies={}  # Explicitly no cookies
        )
        assert response.status_code == 200
        assert response.json() == {"message": "POST success"}

    def test_csrf_ignores_cookie_values(self, client):
        """
        Test that CSRF middleware ignores cookie-based CSRF tokens.

        Verifies:
            - Even if a CSRF cookie exists, middleware uses header
            - Cookie-based CSRF (old model) is not checked
        """
        # Request with CSRF cookie but no header - should fail
        with pytest.raises(Exception) as exc_info:
            client.post(
                "/api/v1/test/post",
                headers={"X-Client-Type": "web"},
                cookies={"csrf_token": "cookie-csrf-token"}
            )
        assert "403" in str(exc_info.value)

        # Request with both cookie and header - header wins
        response = client.post(
            "/api/v1/test/post",
            headers={
                "X-Client-Type": "web",
                "X-CSRF-Token": "header-csrf-token"
            },
            cookies={"csrf_token": "different-cookie-csrf-token"}
        )
        assert response.status_code == 200
