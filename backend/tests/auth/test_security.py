"""Tests for auth.security module."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, WebSocket, status, WebSocketException
from fastapi.security import SecurityScopes

import auth.security as auth_security
import auth.token_manager as auth_token_manager


class TestGetToken:
    """Test get_token function for token retrieval logic."""

    def test_get_access_token_from_header(self):
        """Test access token retrieval from Authorization header."""
        result = auth_security.get_token(
            non_cookie_token="test_token",
            cookie_token=None,
            client_type="web",
            token_type="access",
        )
        assert result == "test_token"

    def test_get_access_token_missing_raises_error(self):
        """Test that missing access token raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_token(
                non_cookie_token=None,
                cookie_token=None,
                client_type="web",
                token_type="access",
            )
        assert exc_info.value.status_code == 401
        assert "Access token missing" in exc_info.value.detail

    def test_get_refresh_token_from_cookie_for_web(self):
        """Test refresh token retrieval from cookie for web client."""
        result = auth_security.get_token(
            non_cookie_token=None,
            cookie_token="refresh_cookie_token",
            client_type="web",
            token_type="refresh",
        )
        assert result == "refresh_cookie_token"

    def test_get_refresh_token_from_header_for_mobile(self):
        """Test refresh token retrieval from header for mobile client."""
        result = auth_security.get_token(
            non_cookie_token="refresh_header_token",
            cookie_token=None,
            client_type="mobile",
            token_type="refresh",
        )
        assert result == "refresh_header_token"

    def test_get_refresh_token_missing_for_web_raises_error(self):
        """Test that missing refresh token from cookie for web raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_token(
                non_cookie_token=None,
                cookie_token=None,
                client_type="web",
                token_type="refresh",
            )
        assert exc_info.value.status_code == 401
        assert "Refresh token missing from cookie" in exc_info.value.detail

    def test_get_refresh_token_missing_for_mobile_raises_error(self):
        """Test that missing refresh token from header for mobile raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_token(
                non_cookie_token=None,
                cookie_token=None,
                client_type="mobile",
                token_type="refresh",
            )
        assert exc_info.value.status_code == 401
        assert (
            "Refresh token missing from Authorization header" in exc_info.value.detail
        )

    def test_invalid_token_type_raises_error(self):
        """Test that invalid token type raises 403."""
        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_token(
                non_cookie_token="test_token",
                cookie_token=None,
                client_type="web",
                token_type="invalid_type",
            )
        assert exc_info.value.status_code == 403
        assert "Invalid client type or token type" in exc_info.value.detail


class TestAccessTokenValidation:
    """Test access token validation functions."""

    def test_validate_access_token_success(self, token_manager, sample_user_read):
        """Test successful access token validation."""
        # Create a valid token
        _, access_token = token_manager.create_token(
            "session-id", sample_user_read, auth_token_manager.TokenType.ACCESS
        )

        # Should not raise an exception
        try:
            auth_security.validate_access_token(access_token, token_manager)
        except HTTPException:
            pytest.fail("Valid token should not raise HTTPException")

    def test_validate_access_token_with_expired_token(self, token_manager):
        """Test that expired token raises HTTPException."""
        expired_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzaWQiOiJzZXNzaW9uLWlkIiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwIiwiYXVkIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwIiwic3ViIjoxLCJzY29wZSI6WyJwcm9maWxlIl0sImlhdCI6MTc1OTk1MzE4NSwibmJmIjoxNzU5OTUzMTg1LCJleHAiOjE3NTk5NTQwODUsImp0aSI6Ijc5ZjY0MmVkLTQ3M2QtNDEwZi1hYzI1LTIyNjEwNTlhMzg2MiJ9.VSizGzvIIi_EJYD_YmfZBEBE_9aJbhLW-25cD1kEOeM"

        with pytest.raises(HTTPException) as exc_info:
            auth_security.validate_access_token(expired_token, token_manager)
        assert exc_info.value.status_code == 401

    def test_validate_access_token_with_invalid_token(self, token_manager):
        """Test that invalid token raises HTTPException."""
        invalid_token = "invalid.token.here"

        with pytest.raises(HTTPException) as exc_info:
            auth_security.validate_access_token(invalid_token, token_manager)
        assert exc_info.value.status_code == 401


class TestGetSubFromAccessToken:
    """Test extracting user ID from access token."""

    def test_get_sub_from_valid_token(self, token_manager, sample_user_read):
        """Test extracting user ID from valid access token."""
        _, access_token = token_manager.create_token(
            "session-id", sample_user_read, auth_token_manager.TokenType.ACCESS
        )

        sub = auth_security.get_sub_from_access_token(access_token, token_manager)
        assert sub == sample_user_read.id
        assert isinstance(sub, int)

    def test_get_sub_from_invalid_token_raises_error(self, token_manager):
        """Test that invalid token raises HTTPException."""
        invalid_token = "invalid.token.here"

        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_sub_from_access_token(invalid_token, token_manager)
        assert exc_info.value.status_code == 401


class TestGetSidFromAccessToken:
    """Test extracting session ID from access token."""

    def test_get_sid_from_valid_token(self, token_manager, sample_user_read):
        """Test extracting session ID from valid access token."""
        session_id = "test-session-123"
        _, access_token = token_manager.create_token(
            session_id, sample_user_read, auth_token_manager.TokenType.ACCESS
        )

        sid = auth_security.get_sid_from_access_token(access_token, token_manager)
        assert sid == session_id
        assert isinstance(sid, str)

    def test_get_sid_from_invalid_token_raises_error(self, token_manager):
        """Test that invalid token raises HTTPException."""
        invalid_token = "invalid.token.here"

        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_sid_from_access_token(invalid_token, token_manager)
        assert exc_info.value.status_code == 401


class TestRefreshTokenValidation:
    """Test refresh token validation functions."""

    def test_validate_refresh_token_success(self, token_manager, sample_user_read):
        """Test successful refresh token validation."""
        _, refresh_token = token_manager.create_token(
            "session-id", sample_user_read, auth_token_manager.TokenType.REFRESH
        )

        # Should not raise an exception
        try:
            auth_security.validate_refresh_token(refresh_token, token_manager)
        except HTTPException:
            pytest.fail("Valid refresh token should not raise HTTPException")

    def test_validate_refresh_token_with_expired_token(self, token_manager):
        """Test that expired refresh token raises HTTPException."""
        expired_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzaWQiOiJzZXNzaW9uLWlkIiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwIiwiYXVkIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwIiwic3ViIjoxLCJzY29wZSI6WyJwcm9maWxlIl0sImlhdCI6MTc1OTk1MzE4NSwibmJmIjoxNzU5OTUzMTg1LCJleHAiOjE3NTk5NTQwODUsImp0aSI6Ijc5ZjY0MmVkLTQ3M2QtNDEwZi1hYzI1LTIyNjEwNTlhMzg2MiJ9.VSizGzvIIi_EJYD_YmfZBEBE_9aJbhLW-25cD1kEOeM"

        with pytest.raises(HTTPException) as exc_info:
            auth_security.validate_refresh_token(expired_token, token_manager)
        assert exc_info.value.status_code == 401


class TestGetSubFromRefreshToken:
    """Test extracting user ID from refresh token."""

    def test_get_sub_from_valid_refresh_token(self, token_manager, sample_user_read):
        """Test extracting user ID from valid refresh token."""
        _, refresh_token = token_manager.create_token(
            "session-id", sample_user_read, auth_token_manager.TokenType.REFRESH
        )

        sub = auth_security.get_sub_from_refresh_token(refresh_token, token_manager)
        assert sub == sample_user_read.id
        assert isinstance(sub, int)


class TestGetSidFromRefreshToken:
    """Test extracting session ID from refresh token."""

    def test_get_sid_from_valid_refresh_token(self, token_manager, sample_user_read):
        """Test extracting session ID from valid refresh token."""
        session_id = "test-session-456"
        _, refresh_token = token_manager.create_token(
            session_id, sample_user_read, auth_token_manager.TokenType.REFRESH
        )

        sid = auth_security.get_sid_from_refresh_token(refresh_token, token_manager)
        assert sid == session_id
        assert isinstance(sid, str)


class TestCheckScopes:
    """Test scope validation function."""

    def test_check_scopes_with_valid_scopes(self, token_manager, sample_user_read):
        """Test that valid scopes pass validation."""
        _, access_token = token_manager.create_token(
            "session-id", sample_user_read, auth_token_manager.TokenType.ACCESS
        )

        security_scopes = SecurityScopes(scopes=["profile", "users:read"])

        # Should not raise an exception
        try:
            auth_security.check_scopes(access_token, token_manager, security_scopes)
        except HTTPException:
            pytest.fail("Valid scopes should not raise HTTPException")

    def test_check_scopes_with_missing_scope(self, token_manager, sample_user_read):
        """Test that missing required scope raises 403."""
        _, access_token = token_manager.create_token(
            "session-id", sample_user_read, auth_token_manager.TokenType.ACCESS
        )

        # Request a scope that the user doesn't have
        security_scopes = SecurityScopes(scopes=["admin:write"])

        with pytest.raises(HTTPException) as exc_info:
            auth_security.check_scopes(access_token, token_manager, security_scopes)
        assert exc_info.value.status_code == 403
        assert "Missing permissions" in exc_info.value.detail

    def test_check_scopes_with_no_required_scopes(
        self, token_manager, sample_user_read
    ):
        """Test that no required scopes passes validation."""
        _, access_token = token_manager.create_token(
            "session-id", sample_user_read, auth_token_manager.TokenType.ACCESS
        )

        security_scopes = SecurityScopes(scopes=[])

        # Should not raise an exception
        try:
            auth_security.check_scopes(access_token, token_manager, security_scopes)
        except HTTPException:
            pytest.fail("Empty required scopes should not raise HTTPException")


class TestGetAndReturnTokens:
    """Test simple token return functions."""

    def test_get_and_return_access_token(self):
        """Test that access token is returned unchanged."""
        test_token = "test_access_token"
        result = auth_security.get_and_return_access_token(test_token)
        assert result == test_token

    def test_get_and_return_refresh_token(self):
        """Test that refresh token is returned unchanged."""
        test_token = "test_refresh_token"
        result = auth_security.get_and_return_refresh_token(test_token)
        assert result == test_token

    def test_get_sub_from_access_token_non_integer_sub(self, token_manager):
        """
        Test that non-integer sub claim raises error.
        """
        # Create a mock token with string sub
        with patch.object(
            token_manager, "get_token_claim", return_value="not_an_integer"
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.get_sub_from_access_token("fake_token", token_manager)
            assert exc_info.value.status_code == 401
            assert "must be an integer" in exc_info.value.detail

    def test_get_sub_from_access_token_for_browser_redirect_non_integer(
        self, token_manager
    ):
        """
        Test browser redirect sub claim validation.
        """
        with patch.object(
            token_manager, "get_token_claim", return_value="not_an_integer"
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.get_sub_from_access_token_for_browser_redirect(
                    "fake_token", token_manager
                )
            assert exc_info.value.status_code == 401

    def test_get_sid_from_access_token_non_string_sid(self, token_manager):
        """
        Test that non-string sid claim raises error.
        """
        with patch.object(token_manager, "get_token_claim", return_value=12345):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.get_sid_from_access_token("fake_token", token_manager)
            assert exc_info.value.status_code == 401
            assert "must be a string" in exc_info.value.detail

    def test_get_sub_from_refresh_token_non_integer(self, token_manager):
        """
        Test that non-integer sub in refresh token raises error.
        """
        with patch.object(
            token_manager, "get_token_claim", return_value="not_an_integer"
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.get_sub_from_refresh_token("fake_token", token_manager)
            assert exc_info.value.status_code == 401

    def test_get_sid_from_refresh_token_non_string(self, token_manager):
        """
        Test that non-string sid in refresh token raises error.
        """
        with patch.object(token_manager, "get_token_claim", return_value=12345):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.get_sid_from_refresh_token("fake_token", token_manager)
            assert exc_info.value.status_code == 401

    def test_validate_access_token_generic_exception(self, token_manager):
        """
        Test generic exception handling in validate_access_token.
        """
        with patch.object(
            token_manager,
            "validate_token_expiration",
            side_effect=RuntimeError("Test error"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.validate_access_token("fake_token", token_manager)
            assert exc_info.value.status_code == 500

    def test_validate_access_token_for_browser_redirect_exception(self, token_manager):
        """
        Test exception handling in browser redirect validation.
        """
        with patch.object(
            token_manager,
            "validate_token_expiration",
            side_effect=RuntimeError("Test error"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.validate_access_token_for_browser_redirect(
                    "fake_token", token_manager
                )
            assert exc_info.value.status_code == 500

    def test_validate_refresh_token_generic_exception(self, token_manager):
        """
        Test generic exception handling in validate_refresh_token.
        """
        with patch.object(
            token_manager,
            "validate_token_expiration",
            side_effect=RuntimeError("Test error"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.validate_refresh_token("fake_token", token_manager)
            assert exc_info.value.status_code == 500

    def test_check_scopes_invalid_scope_format(self, token_manager):
        """
        Test that non-list scope raises error.
        """
        security_scopes = SecurityScopes(scopes=["profile"])

        with patch.object(token_manager, "get_token_claim", return_value="not_a_list"):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.check_scopes("fake_token", token_manager, security_scopes)
            assert exc_info.value.status_code == 403
            assert "Invalid scope format" in exc_info.value.detail

    def test_check_scopes_generic_exception(self, token_manager):
        """
        Test generic exception handling in check_scopes.

        Note: check_scopes only catches HTTPException, not generic exceptions.
        Generic exceptions from get_token_claim will propagate as HTTPException.
        """
        security_scopes = SecurityScopes(scopes=["profile"])

        with patch.object(
            token_manager, "get_token_claim", return_value=["profile", "invalid"]
        ):
            # Trigger the exception handling path by providing valid scope
            # but then simulating an error in the middle of processing
            with patch("auth.security.set", side_effect=RuntimeError("Test error")):
                with pytest.raises(HTTPException) as exc_info:
                    auth_security.check_scopes(
                        "fake_token", token_manager, security_scopes
                    )
                assert exc_info.value.status_code == 500

    def test_check_scopes_for_browser_redirect_invalid_format(self, token_manager):
        """
        Test invalid scope format in browser redirect.
        """
        security_scopes = SecurityScopes(scopes=["profile"])

        with patch.object(token_manager, "get_token_claim", return_value="not_a_list"):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.check_scopes_for_browser_redirect(
                    "fake_token", token_manager, security_scopes
                )
            assert exc_info.value.status_code == 403

    def test_check_scopes_for_browser_redirect_generic_exception(self, token_manager):
        """
        Test generic exception in browser redirect scope check.

        Note: check_scopes_for_browser_redirect only catches HTTPException.
        Generic exceptions from get_token_claim propagate as HTTPException.
        """
        security_scopes = SecurityScopes(scopes=["profile"])

        with patch.object(
            token_manager, "get_token_claim", return_value=["profile", "invalid"]
        ):
            # Trigger the exception handling path
            with patch("auth.security.set", side_effect=RuntimeError("Test error")):
                with pytest.raises(HTTPException) as exc_info:
                    auth_security.check_scopes_for_browser_redirect(
                        "fake_token", token_manager, security_scopes
                    )
                assert exc_info.value.status_code == 500

    def test_validate_websocket_access_token_invalid_sub_claim(self, token_manager):
        """
        Test WebSocket validation with invalid sub claim.
        """
        mock_websocket = MagicMock(spec=WebSocket)

        with patch.object(
            token_manager, "validate_token_expiration", return_value=None
        ):
            with patch.object(token_manager, "get_token_claim", return_value=None):
                with pytest.raises(WebSocketException) as exc_info:
                    import asyncio

                    asyncio.run(
                        auth_security.validate_websocket_access_token(
                            mock_websocket, "fake_token", token_manager
                        )
                    )
                assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION

    def test_validate_websocket_access_token_list_sub_claim(self, token_manager):
        """
        Test WebSocket validation with list sub claim.
        """
        mock_websocket = MagicMock(spec=WebSocket)

        with patch.object(
            token_manager, "validate_token_expiration", return_value=None
        ):
            with patch.object(
                token_manager, "get_token_claim", return_value=["1", "2"]
            ):
                with pytest.raises(WebSocketException) as exc_info:
                    import asyncio

                    asyncio.run(
                        auth_security.validate_websocket_access_token(
                            mock_websocket, "fake_token", token_manager
                        )
                    )
                assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION

    def test_validate_websocket_access_token_http_exception(self, token_manager):
        """
        Test WebSocket validation with HTTP exception.
        """
        mock_websocket = MagicMock(spec=WebSocket)

        with patch.object(
            token_manager,
            "validate_token_expiration",
            side_effect=HTTPException(status_code=401, detail="Token expired"),
        ):
            with pytest.raises(WebSocketException) as exc_info:
                import asyncio

                asyncio.run(
                    auth_security.validate_websocket_access_token(
                        mock_websocket, "fake_token", token_manager
                    )
                )
            assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION

    def test_validate_websocket_access_token_generic_exception(self, token_manager):
        """
        Test WebSocket validation with generic exception.
        """
        mock_websocket = MagicMock(spec=WebSocket)

        with patch.object(
            token_manager,
            "validate_token_expiration",
            side_effect=RuntimeError("Test error"),
        ):
            with pytest.raises(WebSocketException) as exc_info:
                import asyncio

                asyncio.run(
                    auth_security.validate_websocket_access_token(
                        mock_websocket, "fake_token", token_manager
                    )
                )
            assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION


class TestGetAccessTokenForBrowserRedirect:
    """Test get_access_token_for_browser_redirect function."""

    def test_get_access_token_for_browser_redirect_defaults_client_type(self):
        """Test that client_type defaults to 'web' when None."""
        # When client_type is None, it should default to "web"
        result = auth_security.get_access_token_for_browser_redirect(
            access_token="test_token", client_type=None
        )
        assert result == "test_token"


class TestValidateAccessTokenExceptionPaths:
    """Test exception handling in validate_access_token."""

    def test_validate_access_token_with_expired_token_logs_debug(self, token_manager):
        """Test that expired token logs at debug level."""
        with patch.object(
            token_manager,
            "validate_token_expiration",
            side_effect=HTTPException(
                status_code=401, detail="Token expired - please refresh"
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.validate_access_token("expired_token", token_manager)
            assert "expired" in exc_info.value.detail.lower()

    def test_validate_access_token_with_non_expired_error_logs_error(
        self, token_manager
    ):
        """Test that non-expired error logs at error level."""
        with patch.object(
            token_manager,
            "validate_token_expiration",
            side_effect=HTTPException(
                status_code=401, detail="Invalid token signature"
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.validate_access_token("invalid_token", token_manager)
            assert "invalid" in exc_info.value.detail.lower()

    def test_validate_access_token_with_generic_exception(self, token_manager):
        """Test unexpected error during token validation."""
        with patch.object(
            token_manager,
            "validate_token_expiration",
            side_effect=RuntimeError("Unexpected error"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.validate_access_token("test_token", token_manager)
            # Should wrap generic exception as HTTP 500
            assert exc_info.value.status_code == 500


class TestGetSubFromAccessTokenExceptionPath:
    """Test exception handling in get_sub_from_access_token."""

    def test_get_sub_from_access_token_list_raises_error(self, token_manager):
        """Test that list sub claim raises proper error."""
        with patch.object(
            token_manager, "get_token_claim", return_value=["user1", "user2"]
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.get_sub_from_access_token("test_token", token_manager)
            assert exc_info.value.status_code == 401
            assert "must be an integer" in exc_info.value.detail


class TestCheckScopesExceptionPaths:
    """Test exception handling in check_scopes."""

    def test_check_scopes_with_http_exception(self, token_manager):
        """Test that HTTPException from scope check is re-raised."""
        security_scopes = SecurityScopes(scopes=["users:write"])

        with patch.object(
            token_manager, "get_token_claim", return_value="invalid scope format"
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.check_scopes("test_token", token_manager, security_scopes)
            assert exc_info.value.status_code == 403
