"""Tests for the auth._internal.internal_dependencies module."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request, status
from joserfc.errors import MissingClaimError

import modules.auth._internal.internal_dependencies as auth_security
import modules.auth._internal.token_manager as auth_token_manager
import modules.auth.utils as auth_utils
from modules.auth.identity_service import IdentityService
from modules.auth.principal import AccessTokenCred, ApiKeyCred, Principal


def _make_principal(
    user_id: int = 1,
    username: str = "testuser",
    email: str = "test@example.com",
    scopes: frozenset[str] | None = None,
    credential=None,
) -> Principal:
    """Build a test Principal with sensible defaults.

    Args:
        user_id: User primary key.
        username: Username string.
        email: Email address.
        scopes: Granted scopes (defaults to frozenset).
        credential: Credential variant (defaults to
            AccessTokenCred with session-id).

    Returns:
        Principal: Frozen principal for tests.
    """
    return Principal(
        user_id=user_id,
        username=username,
        email=email,
        is_active=True,
        is_superuser=False,
        scopes=scopes if scopes is not None else frozenset(["profile"]),
        credential=(credential if credential is not None else AccessTokenCred(session_id="session-id")),
    )


def _mock_request_with_state() -> MagicMock:
    """Return a mock Request whose state has no cached principal.

    Returns:
        MagicMock: Mock request with a SimpleNamespace state.
    """
    req = MagicMock(spec=Request)
    req.state = SimpleNamespace()
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    req.url = MagicMock()
    req.url.path = "/test"
    return req


class TestGetToken:
    """Test get_token function for token retrieval logic."""

    def test_get_access_token_from_header(self):
        """Test access token retrieval from Authorization header."""
        result = auth_security.get_token(
            non_cookie_token="test_token",
            cookie_token=None,
            client_type="web",
            token_type=auth_token_manager.TokenType.ACCESS,
        )
        assert result == "test_token"

    def test_get_access_token_missing_raises_error(self):
        """Test that missing access token raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_token(
                non_cookie_token=None,
                cookie_token=None,
                client_type="web",
                token_type=auth_token_manager.TokenType.ACCESS,
            )
        assert exc_info.value.status_code == 401
        assert "Access token missing" in exc_info.value.detail

    def test_get_refresh_token_from_cookie_for_web(self):
        """Test refresh token retrieval from cookie for web client."""
        result = auth_security.get_token(
            non_cookie_token=None,
            cookie_token="refresh_cookie_token",
            client_type="web",
            token_type=auth_token_manager.TokenType.REFRESH,
        )
        assert result == "refresh_cookie_token"

    def test_get_refresh_token_from_header_for_mobile(self):
        """Test refresh token retrieval from header for mobile client."""
        result = auth_security.get_token(
            non_cookie_token="refresh_header_token",
            cookie_token=None,
            client_type="mobile",
            token_type=auth_token_manager.TokenType.REFRESH,
        )
        assert result == "refresh_header_token"

    def test_get_refresh_token_missing_for_web_raises_error(self):
        """Test that missing refresh token from cookie for web raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_token(
                non_cookie_token=None,
                cookie_token=None,
                client_type="web",
                token_type=auth_token_manager.TokenType.REFRESH,
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
                token_type=auth_token_manager.TokenType.REFRESH,
            )
        assert exc_info.value.status_code == 401
        assert "Refresh token missing from Authorization header" in exc_info.value.detail

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
            auth_security.validate_access_token_expiration(access_token, token_manager)
        except HTTPException:
            pytest.fail("Valid token should not raise HTTPException")

    def test_validate_access_token_with_expired_token(self, token_manager):
        """Test that expired token raises HTTPException."""
        expired_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzaWQiOiJzZXNzaW9uLWlkIiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwIiwiYXVkIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwIiwic3ViIjoxLCJzY29wZSI6WyJwcm9maWxlIl0sImlhdCI6MTc1OTk1MzE4NSwibmJmIjoxNzU5OTUzMTg1LCJleHAiOjE3NTk5NTQwODUsImp0aSI6Ijc5ZjY0MmVkLTQ3M2QtNDEwZi1hYzI1LTIyNjEwNTlhMzg2MiJ9.VSizGzvIIi_EJYD_YmfZBEBE_9aJbhLW-25cD1kEOeM"

        with pytest.raises(HTTPException) as exc_info:
            auth_security.validate_access_token_expiration(expired_token, token_manager)
        assert exc_info.value.status_code == 401

    def test_validate_access_token_with_invalid_token(self, token_manager):
        """Test that invalid token raises HTTPException."""
        invalid_token = "invalid.token.here"

        with pytest.raises(HTTPException) as exc_info:
            auth_security.validate_access_token_expiration(invalid_token, token_manager)
        assert exc_info.value.status_code == 401


class TestGetSubFromAccessToken:
    """Test extracting user ID from access token."""

    def test_get_sub_from_valid_token(self, sample_user_read):
        """Test extracting user ID via IdentityService."""
        request = _mock_request_with_state()
        principal = _make_principal(user_id=sample_user_read.id)
        mock_service = MagicMock(spec=IdentityService)
        mock_service.resolve_from_access_token.return_value = principal

        result = auth_security.get_sub_from_access_token(request, "fake_token", mock_service)

        assert result == sample_user_read.id
        assert isinstance(result, int)
        assert request.state.principal is principal

    def test_get_sub_caches_principal_on_state(self, sample_user_read):
        """Principal is cached; second call does not re-resolve."""
        request = _mock_request_with_state()
        principal = _make_principal(user_id=sample_user_read.id)
        mock_service = MagicMock(spec=IdentityService)
        mock_service.resolve_from_access_token.return_value = principal

        auth_security.get_sub_from_access_token(request, "fake_token", mock_service)
        # Second call should hit cache
        result2 = auth_security.get_sub_from_access_token(request, "fake_token", mock_service)

        assert result2 == sample_user_read.id
        mock_service.resolve_from_access_token.assert_called_once()

    def test_get_sub_from_invalid_token_raises_error(self):
        """IdentityService 401 propagates to caller."""
        request = _mock_request_with_state()
        mock_service = MagicMock(spec=IdentityService)
        mock_service.resolve_from_access_token.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )

        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_sub_from_access_token(request, "invalid.token", mock_service)
        assert exc_info.value.status_code == 401


class TestGetSidFromAccessToken:
    """Test extracting session ID from access token."""

    def test_get_sid_from_valid_token(self):
        """Test extracting session ID via IdentityService."""
        session_id = "test-session-123"
        request = _mock_request_with_state()
        principal = _make_principal(credential=AccessTokenCred(session_id=session_id))
        mock_service = MagicMock(spec=IdentityService)
        mock_service.resolve_from_access_token.return_value = principal

        sid = auth_security.get_sid_from_access_token(request, "fake_token", mock_service)

        assert sid == session_id
        assert isinstance(sid, str)

    def test_get_sid_non_access_token_cred_raises_error(self):
        """Non-AccessTokenCred credential raises 401."""
        request = _mock_request_with_state()
        principal = _make_principal(credential=ApiKeyCred(api_key_id=1, key_prefix="prefix"))
        mock_service = MagicMock(spec=IdentityService)
        mock_service.resolve_from_access_token.return_value = principal

        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_sid_from_access_token(request, "fake_token", mock_service)
        assert exc_info.value.status_code == 401
        assert "credential type" in exc_info.value.detail

    def test_get_sid_from_invalid_token_raises_error(self):
        """IdentityService 401 propagates to caller."""
        request = _mock_request_with_state()
        mock_service = MagicMock(spec=IdentityService)
        mock_service.resolve_from_access_token.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )

        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_sid_from_access_token(request, "invalid.token", mock_service)
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

    def test_validate_refresh_token_missing_claim_clears_cookies(self):
        """Test missing refresh claims raise the cookie-clearing exception."""

        def raise_missing_claim(*_args):
            try:
                raise MissingClaimError("typ")
            except MissingClaimError as err:
                raise HTTPException(
                    status_code=401,
                    detail="Token is missing required claims.",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from err

        token_manager = MagicMock()
        token_manager.validate_token_expiration.side_effect = raise_missing_claim

        with pytest.raises(auth_utils.ClearRefreshTokenCookieHTTPException) as exc_info:
            auth_security.validate_refresh_token(
                "legacy-refresh-token",
                token_manager,
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


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


class TestGetAndReturnTokens:
    """Test simple token return functions."""

    def test_get_and_return_refresh_token(self):
        """Test that refresh token is returned unchanged."""
        test_token = "test_refresh_token"
        result = auth_security.get_and_return_refresh_token(test_token)
        assert result == test_token

    def test_get_sub_from_access_token_service_raises_401(self):
        """IdentityService failure propagates as 401."""
        request = _mock_request_with_state()
        mock_service = MagicMock(spec=IdentityService)
        mock_service.resolve_from_access_token.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: 'sub' claim must be an integer",
        )

        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_sub_from_access_token(request, "fake_token", mock_service)
        assert exc_info.value.status_code == 401

    def test_get_sid_from_access_token_wrong_cred_type(self):
        """Non-AccessTokenCred raises 401 for SID extraction."""
        request = _mock_request_with_state()
        principal = _make_principal(credential=ApiKeyCred(api_key_id=99, key_prefix="key_"))
        mock_service = MagicMock(spec=IdentityService)
        mock_service.resolve_from_access_token.return_value = principal

        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_sid_from_access_token(request, "fake_token", mock_service)
        assert exc_info.value.status_code == 401
        assert "credential type" in exc_info.value.detail

    def test_get_sub_from_refresh_token_non_integer(self, token_manager):
        """
        Test that non-integer sub in refresh token raises error.
        """
        with patch.object(token_manager, "get_token_claim", return_value="not_an_integer"):
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
                auth_security.validate_access_token_expiration("fake_token", token_manager)
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


class TestValidateAccessTokenExceptionPaths:
    """Test exception handling in validate_access_token."""

    def test_validate_access_token_with_expired_token_logs_debug(self, token_manager):
        """Test that expired token logs at debug level."""
        with patch.object(
            token_manager,
            "validate_token_expiration",
            side_effect=HTTPException(status_code=401, detail="Token expired - please refresh"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.validate_access_token_expiration("expired_token", token_manager)
            assert "expired" in exc_info.value.detail.lower()

    def test_validate_access_token_with_non_expired_error_logs_error(self, token_manager):
        """Test that non-expired error logs at error level."""
        with patch.object(
            token_manager,
            "validate_token_expiration",
            side_effect=HTTPException(status_code=401, detail="Invalid token signature"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.validate_access_token_expiration("invalid_token", token_manager)
            assert "invalid" in exc_info.value.detail.lower()

    def test_validate_access_token_with_generic_exception(self, token_manager):
        """Test unexpected error during token validation."""
        with patch.object(
            token_manager,
            "validate_token_expiration",
            side_effect=RuntimeError("Unexpected error"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_security.validate_access_token_expiration("test_token", token_manager)
            # Should wrap generic exception as HTTP 500
            assert exc_info.value.status_code == 500


class TestGetSubFromAccessTokenExceptionPath:
    """Test exception handling in get_sub_from_access_token."""

    def test_get_sub_from_access_token_service_raises_401(self):
        """IdentityService failure propagates as 401."""
        from types import SimpleNamespace

        request = MagicMock(spec=Request)
        request.state = SimpleNamespace()
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_access_token.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: 'sub' claim must be an integer",
        )
        with pytest.raises(HTTPException) as exc_info:
            auth_security.get_sub_from_access_token(request, "test_token", mock_svc)
        assert exc_info.value.status_code == 401
        assert "must be an integer" in exc_info.value.detail
