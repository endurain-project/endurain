"""Tests for auth.utils module."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Response

import modules.auth.schema as auth_schema
import modules.auth.utils as auth_utils


def _set_cookie_headers(response: Response) -> list[str]:
    """Return all Set-Cookie headers from a response."""
    return [value.decode() for key, value in response.raw_headers if key == b"set-cookie"]


class TestAuthenticateUser:
    """Test user authentication function."""

    def test_authenticate_user_success(self, password_hasher, mock_db, sample_user_read):
        """Test successful user authentication."""
        # Arrange
        username = "testuser"
        password = "TestPassword123!"

        # Create a user with hashed password
        hashed_password = password_hasher.hash_password(password)
        mock_user = MagicMock()
        mock_user.id = sample_user_read.id
        mock_user.username = username
        mock_credential = MagicMock()
        mock_credential.password_hash = hashed_password

        # Mock the CRUD function to return our user
        with (
            patch("modules.auth.utils.users_crud.get_user_by_username", return_value=mock_user),
            patch("modules.auth.utils.auth_credentials_crud.get_credential", return_value=mock_credential),
        ):
            # Act
            result = auth_utils.authenticate_user(username, password, password_hasher, mock_db)

            # Assert
            assert result == mock_user

    def test_authenticate_user_invalid_username(self, password_hasher, mock_db):
        """Test authentication with invalid username raises 401."""
        with patch("modules.auth.utils.users_crud.get_user_by_username", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                auth_utils.authenticate_user("nonexistent", "password", password_hasher, mock_db)
            assert exc_info.value.status_code == 401
            assert "Unable to authenticate" in exc_info.value.detail

    def test_authenticate_user_invalid_password(self, password_hasher, mock_db):
        """Test authentication with invalid password raises 401."""
        # Arrange
        username = "testuser"
        correct_password = "CorrectPassword123!"
        wrong_password = "WrongPassword123!"

        hashed_password = password_hasher.hash_password(correct_password)
        mock_user = MagicMock()
        mock_credential = MagicMock()
        mock_credential.password_hash = hashed_password

        with (
            patch("modules.auth.utils.users_crud.get_user_by_username", return_value=mock_user),
            patch("modules.auth.utils.auth_credentials_crud.get_credential", return_value=mock_credential),
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_utils.authenticate_user(username, wrong_password, password_hasher, mock_db)
            assert exc_info.value.status_code == 401
            assert "Unable to authenticate" in exc_info.value.detail

    def test_authenticate_user_updates_password_hash_if_needed(self, password_hasher, mock_db, sample_user_read):
        """Test that password hash is updated if algorithm changed."""
        # Arrange
        username = "testuser"
        password = "TestPassword123!"

        # Use a different hasher to simulate old hash
        from pwdlib.hashers.bcrypt import BcryptHasher

        old_hasher_instance = BcryptHasher()
        old_hash = old_hasher_instance.hash(password)

        mock_user = MagicMock()
        mock_user.id = sample_user_read.id
        mock_user.username = username
        mock_credential = MagicMock()
        mock_credential.password_hash = old_hash

        with (
            patch("modules.auth.utils.users_crud.get_user_by_username", return_value=mock_user),
            patch("modules.auth.utils.auth_credentials_crud.get_credential", return_value=mock_credential),
            patch("modules.auth.utils.auth_credentials_crud.upsert_password_hash") as mock_edit,
        ):
            # Act
            result = auth_utils.authenticate_user(username, password, password_hasher, mock_db)

            # Assert
            assert result == mock_user
            # Password should be updated since we're using different hasher
            mock_edit.assert_called_once()

    def test_authenticate_user_sso_account_no_password_raises_401(self, password_hasher, mock_db):
        """SSO-only account (no local password) raises 401."""
        mock_user = MagicMock()
        with (
            patch("modules.auth.utils.users_crud.get_user_by_username", return_value=mock_user),
            patch("modules.auth.utils.auth_credentials_crud.get_credential", return_value=None),
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_utils.authenticate_user("ssouser", "anypass", password_hasher, mock_db)
            assert exc_info.value.status_code == 401
            assert "Unable to authenticate" in exc_info.value.detail


class TestCreateTokens:
    """Test token creation function."""

    def test_create_tokens_generates_all_tokens(self, token_manager, sample_user_read):
        """Test that create_tokens generates all required tokens."""
        # Act
        (
            session_id,
            access_token_exp,
            access_token,
            refresh_token_exp,
            refresh_token,
            csrf_token,
        ) = auth_utils.create_tokens(sample_user_read, token_manager)

        # Assert
        assert session_id is not None
        assert isinstance(session_id, str)
        assert len(session_id) > 0

        assert access_token_exp is not None
        assert isinstance(access_token_exp, datetime)
        assert access_token_exp > datetime.now(UTC)

        assert access_token is not None
        assert isinstance(access_token, str)
        assert len(access_token) > 0

        assert refresh_token_exp is not None
        assert isinstance(refresh_token_exp, datetime)
        assert refresh_token_exp > datetime.now(UTC)

        assert refresh_token is not None
        assert isinstance(refresh_token, str)
        assert len(refresh_token) > 0

        assert csrf_token is not None
        assert isinstance(csrf_token, str)
        assert len(csrf_token) >= 32

    def test_create_tokens_with_custom_session_id(self, token_manager, sample_user_read):
        """Test that create_tokens uses provided session ID."""
        # Arrange
        custom_session_id = "custom-session-123"

        # Act
        (
            session_id,
            _,
            _,
            _,
            _,
            _,
        ) = auth_utils.create_tokens(sample_user_read, token_manager, custom_session_id)

        # Assert
        assert session_id == custom_session_id

    def test_create_tokens_refresh_expires_after_access(self, token_manager, sample_user_read):
        """Test that refresh token expires after access token."""
        # Act
        (
            _,
            access_token_exp,
            _,
            refresh_token_exp,
            _,
            _,
        ) = auth_utils.create_tokens(sample_user_read, token_manager)

        # Assert
        assert refresh_token_exp > access_token_exp

    def test_create_tokens_generates_unique_tokens(self, token_manager, sample_user_read):
        """Test that multiple calls generate unique tokens."""
        # Act
        (_, _, access_token1, _, refresh_token1, csrf_token1) = auth_utils.create_tokens(
            sample_user_read, token_manager
        )
        (_, _, access_token2, _, refresh_token2, csrf_token2) = auth_utils.create_tokens(
            sample_user_read, token_manager
        )

        # Assert
        assert access_token1 != access_token2
        assert refresh_token1 != refresh_token2
        assert csrf_token1 != csrf_token2


class TestCompleteLogin:
    """Test complete_login function."""

    def test_complete_login_for_web_client(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """Test complete_login for web client sets cookies and returns tokens."""
        # Arrange
        response = Response()
        client_type = "web"

        with patch("modules.auth.utils.auth_sessions_utils.create_session"):
            # Act
            result = auth_utils.complete_login(
                response,
                mock_request,
                sample_user_read,
                client_type,
                password_hasher,
                token_manager,
                mock_db,
            )

        # Assert
        assert "session_id" in result
        assert "access_token" in result
        assert "csrf_token" in result
        assert "token_type" in result
        assert "expires_in" in result

        assert result["token_type"] == "bearer"
        assert isinstance(result["expires_in"], int)

        # Check that refresh token cookie was set
        assert "endurain_refresh_token" in response.headers.get("set-cookie", "")

    def test_complete_login_for_mobile_client(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """Test complete_login for mobile client returns tokens without CSRF token."""
        # Arrange
        response = Response()
        client_type = "mobile"

        with patch("modules.auth.utils.auth_sessions_utils.create_session"):
            # Act
            result = auth_utils.complete_login(
                response,
                mock_request,
                sample_user_read,
                client_type,
                password_hasher,
                token_manager,
                mock_db,
            )

        # Assert
        assert "session_id" in result
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["token_type"] == "bearer"
        # Mobile clients don't need CSRF tokens
        assert "csrf_token" not in result

    def test_complete_login_creates_session(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """Test that complete_login creates a session in the database."""
        # Arrange
        response = Response()
        client_type = "web"

        with patch("modules.auth.utils.auth_sessions_utils.create_session") as mock_create_session:
            # Act
            result = auth_utils.complete_login(
                response,
                mock_request,
                sample_user_read,
                client_type,
                password_hasher,
                token_manager,
                mock_db,
            )

        # Assert
        mock_create_session.assert_called_once()
        call_args = mock_create_session.call_args

        # Verify session_id matches
        assert call_args[0][0] == result["session_id"]
        # Verify user was passed
        assert call_args[0][1] == sample_user_read
        # Verify request was passed
        assert call_args[0][2] == mock_request

    def test_complete_login_invalid_client_type_raises_error(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """Test that invalid client type raises 403."""
        # Arrange
        response = Response()
        invalid_client_type = "invalid"

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            auth_utils.complete_login(
                response,
                mock_request,
                sample_user_read,
                invalid_client_type,
                password_hasher,
                token_manager,
                mock_db,
            )
        assert exc_info.value.status_code == 403
        assert "Invalid client type" in exc_info.value.detail

    def test_complete_login_sets_secure_cookie_for_production(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """Test that secure flag is set on cookie when ENVIRONMENT is production."""
        # Arrange
        response = Response()
        client_type = "web"

        with (
            patch("modules.auth.utils.auth_sessions_utils.create_session"),
            patch("modules.auth.utils.core_config.settings.ENVIRONMENT", "production"),
        ):
            # Act
            auth_utils.complete_login(
                response,
                mock_request,
                sample_user_read,
                client_type,
                password_hasher,
                token_manager,
                mock_db,
            )

        # Assert
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "secure" in set_cookie_header.lower()

    def test_complete_login_omits_secure_cookie_for_development(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """Test that secure flag is omitted from cookie when ENVIRONMENT is development."""
        # Arrange
        response = Response()
        client_type = "web"

        with (
            patch("modules.auth.utils.auth_sessions_utils.create_session"),
            patch("modules.auth.utils.core_config.settings.ENVIRONMENT", "development"),
        ):
            # Act
            auth_utils.complete_login(
                response,
                mock_request,
                sample_user_read,
                client_type,
                password_hasher,
                token_manager,
                mock_db,
            )

        # Assert
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "secure" not in set_cookie_header.lower()

    def test_complete_login_cookie_attributes(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """Test that refresh token cookie has correct security attributes."""
        # Arrange
        response = Response()
        client_type = "web"

        with patch("modules.auth.utils.auth_sessions_utils.create_session"):
            # Act
            auth_utils.complete_login(
                response,
                mock_request,
                sample_user_read,
                client_type,
                password_hasher,
                token_manager,
                mock_db,
            )

        # Assert
        set_cookie_header = _set_cookie_headers(response)[-1]
        assert "endurain_refresh_token" in set_cookie_header
        assert "httponly" in set_cookie_header.lower()
        assert "samesite=strict" in set_cookie_header.lower()
        assert "path=/api/v1/auth" in set_cookie_header.lower()

    def test_set_refresh_token_cookie_clears_legacy_paths(self):
        """Test setting a refresh cookie clears all known old paths."""
        response = Response()

        auth_utils.set_refresh_token_cookie(response, "new-refresh-token")

        set_cookie_headers = [header.lower() for header in _set_cookie_headers(response)]
        assert any(
            "endurain_refresh_token" in header and "max-age=0" in header and "path=/;" in header
            for header in set_cookie_headers
        )
        assert any(
            "endurain_refresh_token" in header and "max-age=0" in header and "path=/api/v1/auth" in header
            for header in set_cookie_headers
        )
        assert set_cookie_headers[-1].startswith("endurain_refresh_token=new-refresh-token")
        assert "path=/api/v1/auth" in set_cookie_headers[-1]

    @pytest.mark.asyncio
    async def test_clear_refresh_token_cookie_exception_handler(self):
        """Test missing-claim errors clear all refresh cookie paths."""
        exc = auth_utils.ClearRefreshTokenCookieHTTPException(
            status_code=401,
            detail="Token is missing required claims.",
            headers={"WWW-Authenticate": "Bearer"},
        )

        response = await auth_utils.clear_refresh_token_cookie_exception_handler(
            MagicMock(),
            exc,
        )

        set_cookie_headers = [header.lower() for header in _set_cookie_headers(response)]
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert any("max-age=0" in h and "path=/;" in h for h in set_cookie_headers)
        assert any("max-age=0" in h and "path=/api/v1/auth" in h for h in set_cookie_headers)

    def test_complete_login_returns_different_tokens_on_each_call(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """Test that each login generates unique tokens."""
        # Arrange
        response1 = Response()
        response2 = Response()
        client_type = "web"

        with patch("modules.auth.utils.auth_sessions_utils.create_session"):
            # Act
            result1 = auth_utils.complete_login(
                response1,
                mock_request,
                sample_user_read,
                client_type,
                password_hasher,
                token_manager,
                mock_db,
            )

            result2 = auth_utils.complete_login(
                response2,
                mock_request,
                sample_user_read,
                client_type,
                password_hasher,
                token_manager,
                mock_db,
            )

        # Assert
        assert result1["session_id"] != result2["session_id"]
        assert result1["access_token"] != result2["access_token"]
        assert result1["csrf_token"] != result2["csrf_token"]


class TestIsSecureCookieEnvironment:
    """Tests for _is_secure_cookie_environment."""

    def test_returns_true_when_production(self):
        with patch.object(auth_utils.core_config.settings, "ENVIRONMENT", "production"):
            assert auth_utils._is_secure_cookie_environment() is True

    def test_returns_true_when_demo(self):
        with patch.object(auth_utils.core_config.settings, "ENVIRONMENT", "demo"):
            assert auth_utils._is_secure_cookie_environment() is True

    def test_returns_false_when_development(self):
        with patch.object(auth_utils.core_config.settings, "ENVIRONMENT", "development"):
            assert auth_utils._is_secure_cookie_environment() is False


class TestClearRefreshTokenCookies:
    """Tests for clear_refresh_token_cookies."""

    def test_clears_cookies_on_all_paths(self):
        response = Response()
        auth_utils.clear_refresh_token_cookies(response)
        expected_paths = auth_utils.REFRESH_TOKEN_COOKIE_CLEAR_PATHS
        set_cookie_headers = [v.decode().lower() for k, v in response.raw_headers if k == b"set-cookie"]
        for path in expected_paths:
            assert any(
                "endurain_refresh_token" in h and "max-age=0" in h and f"path={path}" in h for h in set_cookie_headers
            ), f"Missing clear for path {path}"

    def test_uses_secure_httponly_samesite_attributes(self):
        response = Response()
        auth_utils.clear_refresh_token_cookies(response)
        set_cookie_headers = [v.decode() for k, v in response.raw_headers if k == b"set-cookie"]
        for header in set_cookie_headers:
            lower = header.lower()
            assert "httponly" in lower
            assert "samesite=strict" in lower


class TestCreateMobilePkceSessionResponse:
    """Tests for create_mobile_pkce_session_response."""

    def test_invalid_code_challenge_method_raises_400(self, password_hasher, mock_db):
        with pytest.raises(HTTPException) as exc_info:
            auth_utils.create_mobile_pkce_session_response(
                response=Response(),
                request=MagicMock(),
                user=MagicMock(),
                code_challenge="abc",
                code_challenge_method="plain",
                password_hasher=password_hasher,
                db=mock_db,
            )
        assert exc_info.value.status_code == 400

    def test_valid_code_challenge_creates_session(self, password_hasher, mock_db):
        response = Response()
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_user = MagicMock()
        mock_user.id = 1

        with (
            patch("modules.auth.utils.idp_utils.validate_pkce_challenge"),
            patch("modules.auth.utils.oauth_state_crud.create_oauth_state"),
            patch("modules.auth.utils.auth_sessions_utils.create_session"),
        ):
            result = auth_utils.create_mobile_pkce_session_response(
                response=response,
                request=mock_request,
                user=mock_user,
                code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                code_challenge_method="S256",
                password_hasher=password_hasher,
                db=mock_db,
            )

        assert isinstance(result, auth_schema.MobileSessionResponse)
        assert result.session_id is not None
        assert result.mfa_required is False
