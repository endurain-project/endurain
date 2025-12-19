"""Tests for auth.security module."""

import pytest
from fastapi import HTTPException
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
