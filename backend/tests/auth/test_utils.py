"""Tests for auth.utils module."""

import dataclasses
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Response

import core.exceptions as core_exceptions
import modules.auth.authentication.dependencies as auth_transport_dependencies
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.service as auth_utils
import modules.auth.authentication.token_service as auth_utils_token_service
import modules.auth.computation as auth_computation
from modules.auth.constants import ClientType


@pytest.fixture(autouse=True)
def _session_policy(session_policy):
    """Serve the default session policy instead of reading it from the database."""
    with patch(
        "modules.auth.authentication.service.server_settings_integration.get_session_policy",
        return_value=session_policy,
    ):
        yield


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
            patch("modules.auth.authentication.service.users_integration.get_user_by_username", return_value=mock_user),
            patch(
                "modules.auth.authentication.service.credentials_integration.get_credential",
                return_value=mock_credential,
            ),
        ):
            # Act
            result = auth_utils.authenticate_user(mock_user, username, password, password_hasher, mock_db)

            # Assert
            assert result == mock_user

    def test_authenticate_user_invalid_username(self, password_hasher, mock_db):
        """Test authentication with invalid username raises 401."""
        with patch("modules.auth.authentication.service.users_integration.get_user_by_username", return_value=None):
            with pytest.raises(core_exceptions.DomainError) as exc_info:
                auth_utils.authenticate_user(None, "nonexistent", "password", password_hasher, mock_db)
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
            patch("modules.auth.authentication.service.users_integration.get_user_by_username", return_value=mock_user),
            patch(
                "modules.auth.authentication.service.credentials_integration.get_credential",
                return_value=mock_credential,
            ),
        ):
            with pytest.raises(core_exceptions.DomainError) as exc_info:
                auth_utils.authenticate_user(mock_user, username, wrong_password, password_hasher, mock_db)
            assert exc_info.value.status_code == 401
            assert "Unable to authenticate" in exc_info.value.detail

    def test_authenticate_user_refuses_a_bcrypt_hash_like_a_wrong_password(self, password_hasher, mock_db):
        """A leftover bcrypt hash is refused with 401 and the credential is left untouched."""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_credential = MagicMock()
        mock_credential.password_hash = "$2b$12$C6UzMDM.H6dfI/f/IKcEeO5lC7Zq3o1m1u0YF1kXJq8r9eJ8q7y6e"

        with (
            patch("modules.auth.authentication.service.users_integration.get_user_by_username", return_value=mock_user),
            patch(
                "modules.auth.authentication.service.credentials_integration.get_credential",
                return_value=mock_credential,
            ),
            patch("modules.auth.authentication.service.credentials_integration.set_local_password_hash") as mock_edit,
        ):
            with pytest.raises(core_exceptions.UnauthenticatedError):
                auth_utils.authenticate_user(mock_user, "testuser", "TestPassword123!", password_hasher, mock_db)

            mock_edit.assert_not_called()

    def test_authenticate_user_sso_account_no_password_raises_401(self, password_hasher, mock_db):
        """SSO-only account (no local password) raises 401."""
        mock_user = MagicMock()
        with (
            patch("modules.auth.authentication.service.users_integration.get_user_by_username", return_value=mock_user),
            patch("modules.auth.authentication.service.credentials_integration.get_credential", return_value=None),
        ):
            with pytest.raises(core_exceptions.DomainError) as exc_info:
                auth_utils.authenticate_user(mock_user, "ssouser", "anypass", password_hasher, mock_db)
            assert exc_info.value.status_code == 401
            assert "Unable to authenticate" in exc_info.value.detail


class TestCreateTokens:
    """Test token creation function."""

    def test_create_tokens_generates_all_tokens(self, token_manager, sample_user_read, session_policy):
        """Test that create_tokens generates all required tokens."""
        # Act
        (
            session_id,
            access_token_exp,
            access_token,
            refresh_token_exp,
            refresh_token,
            csrf_token,
        ) = auth_utils_token_service.create_tokens(sample_user_read, ClientType.WEB, token_manager, session_policy)

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

    def test_create_tokens_with_custom_session_id(self, token_manager, sample_user_read, session_policy):
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
        ) = auth_utils_token_service.create_tokens(
            sample_user_read, ClientType.WEB, token_manager, session_policy, custom_session_id
        )

        # Assert
        assert session_id == custom_session_id

    def test_create_tokens_refresh_expires_after_access(self, token_manager, sample_user_read, session_policy):
        """Test that refresh token expires after access token."""
        # Act
        (
            _,
            access_token_exp,
            _,
            refresh_token_exp,
            _,
            _,
        ) = auth_utils_token_service.create_tokens(sample_user_read, ClientType.WEB, token_manager, session_policy)

        # Assert
        assert refresh_token_exp > access_token_exp

    def test_create_tokens_generates_unique_tokens(self, token_manager, sample_user_read, session_policy):
        """Test that multiple calls generate unique tokens."""
        # Act
        (_, _, access_token1, _, refresh_token1, csrf_token1) = auth_utils_token_service.create_tokens(
            sample_user_read, ClientType.WEB, token_manager, session_policy
        )
        (_, _, access_token2, _, refresh_token2, csrf_token2) = auth_utils_token_service.create_tokens(
            sample_user_read, ClientType.WEB, token_manager, session_policy
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

        with patch(
            "modules.auth.authentication.service.sessions_integration.create_session",
            return_value=MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30)),
        ):
            # Act
            outcome = auth_utils.complete_login(
                "127.0.0.1",
                "pytest-agent",
                sample_user_read,
                password_hasher,
                token_manager,
                mock_db,
                mfa=False,
            )
            result = authentication_dependencies.deliver_auth_outcome(response, outcome).model_dump()

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

    def test_a_mobile_token_body_carries_every_token_and_no_csrf_token(self):
        """The mobile body, as the token exchange and a refresh answer it, holds the refresh token."""
        now = datetime.now(UTC)

        outcome = auth_utils_token_service.build_mobile_token_response(
            "sid", "at", now + timedelta(minutes=15), "rt", now + timedelta(days=7), now + timedelta(days=30)
        )

        result = outcome.body.model_dump()
        assert result["refresh_token"] == "rt"
        assert result["token_type"] == "bearer"
        assert "csrf_token" not in result
        assert outcome.refresh_cookie is None

    def test_complete_login_creates_session(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """Test that complete_login creates a session in the database."""
        # Arrange
        response = Response()

        with patch(
            "modules.auth.authentication.service.sessions_integration.create_session",
            return_value=MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30)),
        ) as mock_create_session:
            # Act
            outcome = auth_utils.complete_login(
                "127.0.0.1",
                "pytest-agent",
                sample_user_read,
                password_hasher,
                token_manager,
                mock_db,
                mfa=False,
            )
            result = authentication_dependencies.deliver_auth_outcome(response, outcome).model_dump()

        # Assert
        mock_create_session.assert_called_once()
        call_args = mock_create_session.call_args

        # Verify session_id matches
        assert call_args[0][0] == result["session_id"]
        # Verify user was passed
        assert call_args[0][1] == sample_user_read
        # A password sign-in that answers tokens is a web client's
        assert call_args[0][2] == ClientType.WEB
        # Verify the client address and user agent were passed
        assert call_args[0][3] == "127.0.0.1"
        assert call_args[0][4] == "pytest-agent"

    def test_complete_login_uses_the_policy_lifetimes_for_tokens_cookie_and_session(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request, session_policy
    ):
        """The session and the cookie expire with the refresh token, whose lifetime is the policy's."""
        policy = dataclasses.replace(
            session_policy, access_token_ttl=timedelta(minutes=5), refresh_token_ttl=timedelta(days=3)
        )
        response = Response()

        with (
            patch(
                "modules.auth.authentication.service.server_settings_integration.get_session_policy",
                return_value=policy,
            ),
            patch(
                "modules.auth.authentication.service.sessions_integration.create_session",
                return_value=MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30)),
            ) as mock_create_session,
        ):
            outcome = auth_utils.complete_login(
                "127.0.0.1",
                "pytest-agent",
                sample_user_read,
                password_hasher,
                token_manager,
                mock_db,
                mfa=False,
            )
            result = authentication_dependencies.deliver_auth_outcome(response, outcome).model_dump()

        assert result["expires_in"] == pytest.approx(300, abs=2)
        assert result["refresh_token_expires_in"] == pytest.approx(3 * 86400, abs=2)
        session_expiry = mock_create_session.call_args.args[7]
        assert session_expiry - datetime.now(UTC) == pytest.approx(timedelta(days=3), abs=timedelta(seconds=2))
        cookie = _set_cookie_headers(response)[-1].lower()
        assert f"{session_expiry:%d %b %Y}".lower() in cookie

    def test_complete_login_tells_the_client_the_sessions_capped_expiry(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """A session capped below the refresh token's lifetime is what the body and the cookie report."""
        session_expiry = datetime.now(UTC) + timedelta(hours=2)
        response = Response()

        with patch(
            "modules.auth.authentication.service.sessions_integration.create_session",
            return_value=MagicMock(expires_at=session_expiry),
        ):
            outcome = auth_utils.complete_login(
                "127.0.0.1",
                "pytest-agent",
                sample_user_read,
                password_hasher,
                token_manager,
                mock_db,
                mfa=False,
            )
            result = authentication_dependencies.deliver_auth_outcome(response, outcome).model_dump()

        assert result["refresh_token_expires_in"] == pytest.approx(2 * 3600, abs=2)
        assert outcome.refresh_cookie.expires_at == session_expiry

    def test_set_refresh_token_cookie_expires_at_the_given_time(self):
        response = Response()

        auth_transport_dependencies.set_refresh_token_cookie(
            response, "tok", datetime(2031, 1, 5, 12, 0, tzinfo=UTC), environment="development"
        )

        assert "05 jan 2031 12:00:00 gmt" in _set_cookie_headers(response)[-1].lower()

    def test_complete_login_sets_secure_cookie_for_production(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """Test that secure flag is set on cookie when ENVIRONMENT is production."""
        # Arrange
        response = Response()

        with (
            patch(
                "modules.auth.authentication.service.sessions_integration.create_session",
                return_value=MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30)),
            ),
            patch("modules.auth.authentication.dependencies.core_config.settings.ENVIRONMENT", "production"),
        ):
            # Act
            outcome = auth_utils.complete_login(
                "127.0.0.1",
                "pytest-agent",
                sample_user_read,
                password_hasher,
                token_manager,
                mock_db,
                mfa=False,
            )
            authentication_dependencies.deliver_auth_outcome(response, outcome)

        # Assert
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "secure" in set_cookie_header.lower().removeprefix("__host-")
        assert "__Host-endurain_refresh_token=" in set_cookie_header

    def test_complete_login_omits_secure_cookie_for_development(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """Test that secure flag is omitted from cookie when ENVIRONMENT is development."""
        # Arrange
        response = Response()

        with (
            patch(
                "modules.auth.authentication.service.sessions_integration.create_session",
                return_value=MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30)),
            ),
            patch("modules.auth.authentication.dependencies.core_config.settings.ENVIRONMENT", "development"),
        ):
            # Act
            outcome = auth_utils.complete_login(
                "127.0.0.1",
                "pytest-agent",
                sample_user_read,
                password_hasher,
                token_manager,
                mock_db,
                mfa=False,
            )
            authentication_dependencies.deliver_auth_outcome(response, outcome)

        # Assert
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "secure" not in set_cookie_header.lower()
        assert "endurain_refresh_token=" in set_cookie_header

    def test_complete_login_cookie_attributes(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """Test that refresh token cookie has correct security attributes."""
        # Arrange
        response = Response()

        with patch(
            "modules.auth.authentication.service.sessions_integration.create_session",
            return_value=MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30)),
        ):
            # Act
            outcome = auth_utils.complete_login(
                "127.0.0.1",
                "pytest-agent",
                sample_user_read,
                password_hasher,
                token_manager,
                mock_db,
                mfa=False,
            )
            authentication_dependencies.deliver_auth_outcome(response, outcome)

        # Assert
        set_cookie_header = _set_cookie_headers(response)[-1]
        assert "endurain_refresh_token" in set_cookie_header
        assert "httponly" in set_cookie_header.lower()
        assert "samesite=strict" in set_cookie_header.lower()
        assert "path=/;" in f"{set_cookie_header.lower()};"
        assert "domain" not in set_cookie_header.lower()

    def test_set_refresh_token_cookie_clears_the_old_value(self):
        """Test setting a refresh cookie first clears the cookie it replaces."""
        response = Response()

        auth_transport_dependencies.set_refresh_token_cookie(
            response, "new-refresh-token", datetime.now(UTC) + timedelta(days=7), environment="development"
        )

        set_cookie_headers = [header.lower() for header in _set_cookie_headers(response)]
        assert any(
            "endurain_refresh_token" in header and "max-age=0" in header and "path=/;" in header
            for header in set_cookie_headers
        )
        assert set_cookie_headers[-1].startswith("endurain_refresh_token=new-refresh-token")
        assert "path=/;" in set_cookie_headers[-1]

    @pytest.mark.parametrize("environment", ["production", "demo"])
    def test_deployed_refresh_cookie_meets_host_prefix_rules(self, environment):
        """The ``__Host-`` prefix needs Secure, Path=/ and no Domain on every cookie set under that name."""
        response = Response()

        auth_transport_dependencies.set_refresh_token_cookie(
            response, "new-refresh-token", datetime.now(UTC) + timedelta(days=7), environment=environment
        )

        host_headers = [header for header in _set_cookie_headers(response) if header.startswith("__Host-")]
        assert host_headers
        for header in host_headers:
            assert header.startswith("__Host-endurain_refresh_token=")
            attributes = [part.strip().lower() for part in header.split(";")[1:]]
            assert "secure" in attributes
            assert "path=/" in attributes
            assert not any(part.startswith("domain") for part in attributes)
        assert not any(header.startswith("__Secure-") for header in _set_cookie_headers(response))

    @pytest.mark.asyncio
    async def test_clear_refresh_token_cookie_exception_handler(self):
        """Test missing-claim errors clear the refresh cookie."""
        exc = auth_transport_dependencies.ClearRefreshTokenCookieError("Token is missing required claims.")

        request = MagicMock()
        request.url.path = "/api/v1/auth/refresh"
        response = await auth_transport_dependencies.clear_refresh_token_cookie_exception_handler(
            request,
            exc,
        )

        set_cookie_headers = [header.lower() for header in _set_cookie_headers(response)]
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'
        assert response.headers["content-type"].startswith("application/problem+json")
        assert b"urn:endurain:error:invalid-token" in response.body
        assert any("max-age=0" in h and "path=/;" in h for h in set_cookie_headers)

    def test_complete_login_returns_different_tokens_on_each_call(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """Test that each login generates unique tokens."""
        # Arrange
        response1 = Response()
        response2 = Response()

        with patch(
            "modules.auth.authentication.service.sessions_integration.create_session",
            return_value=MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30)),
        ):
            # Act
            outcome = auth_utils.complete_login(
                "127.0.0.1",
                "pytest-agent",
                sample_user_read,
                password_hasher,
                token_manager,
                mock_db,
                mfa=False,
            )
            result1 = authentication_dependencies.deliver_auth_outcome(response1, outcome).model_dump()

            outcome = auth_utils.complete_login(
                "127.0.0.1",
                "pytest-agent",
                sample_user_read,
                password_hasher,
                token_manager,
                mock_db,
                mfa=False,
            )
            result2 = authentication_dependencies.deliver_auth_outcome(response2, outcome).model_dump()

        # Assert
        assert result1["session_id"] != result2["session_id"]
        assert result1["access_token"] != result2["access_token"]
        assert result1["csrf_token"] != result2["csrf_token"]


class TestDeliverAuthOutcome:
    """Test deliver_auth_outcome function."""

    def test_marks_token_response_as_not_cacheable(self):
        """Token responses carry Cache-Control: no-store and Pragma: no-cache (RFC 6749 5.1)."""
        response = Response()
        outcome = auth_schema.AuthOutcome(body={"access_token": "token"})

        authentication_dependencies.deliver_auth_outcome(response, outcome)

        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"


class TestIsSecureCookieEnvironment:
    """Tests for secure_cookie."""

    def test_returns_true_when_production(self):
        with patch.object(auth_transport_dependencies.core_config.settings, "ENVIRONMENT", "production"):
            assert auth_computation.secure_cookie(auth_transport_dependencies.core_config.settings.ENVIRONMENT) is True

    def test_returns_true_when_demo(self):
        with patch.object(auth_transport_dependencies.core_config.settings, "ENVIRONMENT", "demo"):
            assert auth_computation.secure_cookie(auth_transport_dependencies.core_config.settings.ENVIRONMENT) is True

    def test_returns_false_when_development(self):
        with patch.object(auth_transport_dependencies.core_config.settings, "ENVIRONMENT", "development"):
            assert auth_computation.secure_cookie(auth_transport_dependencies.core_config.settings.ENVIRONMENT) is False


class TestClearRefreshTokenCookies:
    """Tests for clear_refresh_token_cookies."""

    def test_clears_the_cookie_on_its_path(self):
        response = Response()
        authentication_dependencies.clear_refresh_token_cookies(response, environment="development")
        path = auth_transport_dependencies.REFRESH_TOKEN_COOKIE_PATH
        set_cookie_headers = [v.decode().lower() for k, v in response.raw_headers if k == b"set-cookie"]
        assert any(
            "endurain_refresh_token" in h and "max-age=0" in h and f"path={path};" in h for h in set_cookie_headers
        )

    def test_uses_secure_httponly_samesite_attributes(self):
        response = Response()
        authentication_dependencies.clear_refresh_token_cookies(response, environment="development")
        set_cookie_headers = [v.decode() for k, v in response.raw_headers if k == b"set-cookie"]
        for header in set_cookie_headers:
            lower = header.lower()
            assert "httponly" in lower
            assert "samesite=strict" in lower


class TestPasswordAmr:
    def test_a_password_alone_is_pwd(self):
        assert auth_utils.password_amr(mfa=False) == ["pwd"]

    def test_a_second_factor_adds_otp_and_mfa(self):
        assert auth_utils.password_amr(mfa=True) == ["pwd", "otp", "mfa"]


class TestCreateMobilePkceSessionResponse:
    """Tests for create_mobile_pkce_session_response."""

    def test_invalid_code_challenge_method_raises_400(self, password_hasher, mock_db):
        with pytest.raises(core_exceptions.DomainError) as exc_info:
            auth_utils.create_mobile_pkce_session_response(
                ip_address="127.0.0.1",
                user_agent="pytest-agent",
                user=MagicMock(),
                code_challenge="abc",
                code_challenge_method="plain",
                password_hasher=password_hasher,
                db=mock_db,
                security_generation=0,
                mfa=False,
            )
        assert exc_info.value.status_code == 400

    def test_valid_code_challenge_creates_session(self, password_hasher, mock_db):
        mock_user = MagicMock()
        mock_user.id = 1

        with (
            patch("modules.auth.authentication.service.auth_computation.validate_pkce_challenge"),
            patch("modules.auth.authentication.service.oauth_state_integration.create_oauth_state"),
            patch(
                "modules.auth.authentication.service.sessions_integration.create_session",
                return_value=MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30)),
            ) as create_session,
        ):
            result = auth_utils.create_mobile_pkce_session_response(
                ip_address="127.0.0.1",
                user_agent="pytest-agent",
                user=mock_user,
                code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                code_challenge_method="S256",
                password_hasher=password_hasher,
                db=mock_db,
                security_generation=0,
                mfa=False,
            )

        assert isinstance(result, auth_schema.MobileSessionRead)
        assert result.session_id is not None
        assert result.next_step == "exchange"
        assert create_session.call_args.args[2] == ClientType.MOBILE
