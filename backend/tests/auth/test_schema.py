"""
Tests for auth.schema module and auth router error responses.

Store behaviour (login/MFA/step-up lockout) is covered in
``tests/auth/lockout/test_lockout.py``; this module keeps the Pydantic schema
tests and the router-level error-path tests.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

import core.exceptions as core_exceptions
import modules.auth.authentication.public_router as auth_router
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.service as auth_service


class TestLoginRequest:
    """Tests for LoginRequest Pydantic model."""

    def test_login_request_valid(self):
        """Test valid login request."""
        request = auth_schema.LoginRequest(username="testuser", password="Password1!")
        assert request.username == "testuser"
        assert request.password == "Password1!"

    def test_login_request_username_too_short(self):
        """Test login request with empty username."""
        with pytest.raises(ValidationError) as exc_info:
            auth_schema.LoginRequest(username="", password="Password1!")
        assert "username" in str(exc_info.value)

    def test_login_request_username_too_long(self):
        """Test login request with username exceeding max length."""
        with pytest.raises(ValidationError) as exc_info:
            auth_schema.LoginRequest(username="a" * 251, password="Password1!")
        assert "username" in str(exc_info.value)

    def test_login_request_password_too_short(self):
        """Test login request with password less than 8 characters."""
        with pytest.raises(ValidationError) as exc_info:
            auth_schema.LoginRequest(username="testuser", password="Pass1!")
        assert "password" in str(exc_info.value)


class TestMFALoginRequest:
    """Tests for MFALoginRequest Pydantic model."""

    def test_mfa_login_request_valid(self):
        """Test valid MFA login request with 6-digit code."""
        request = auth_schema.MFALoginRequest(mfa_challenge="c" * 43, mfa_code="123456")
        assert request.mfa_challenge == "c" * 43
        assert request.mfa_code == "123456"

    def test_mfa_login_request_invalid_code_format_letters(self):
        """Test MFA login request with non-numeric code."""
        with pytest.raises(ValidationError) as exc_info:
            auth_schema.MFALoginRequest(mfa_challenge="c" * 43, mfa_code="12345a")
        assert "mfa_code" in str(exc_info.value)

    def test_mfa_login_request_invalid_code_too_short(self):
        """Test MFA login request with code less than 6 digits."""
        with pytest.raises(ValidationError) as exc_info:
            auth_schema.MFALoginRequest(mfa_challenge="c" * 43, mfa_code="12345")
        assert "mfa_code" in str(exc_info.value)

    def test_mfa_login_request_invalid_code_too_long(self):
        """Test MFA login request with code more than 6 digits."""
        with pytest.raises(ValidationError) as exc_info:
            auth_schema.MFALoginRequest(mfa_challenge="c" * 43, mfa_code="1234567")
        assert "mfa_code" in str(exc_info.value)


class TestMFARequiredResponse:
    """Tests for MFARequiredRead Pydantic model."""

    def test_mfa_required_response_defaults(self):
        """Test MFA required response with default values."""
        response = auth_schema.MFARequiredRead(username="testuser", mfa_challenge="c" * 43)
        assert response.mfa_required is True
        assert response.username == "testuser"
        assert response.message == "MFA verification required"

    def test_mfa_required_response_custom_message(self):
        """Test MFA required response with custom message."""
        response = auth_schema.MFARequiredRead(
            username="testuser", mfa_challenge="c" * 43, message="Custom MFA message"
        )
        assert response.mfa_required is True
        assert response.message == "Custom MFA message"

    def test_mfa_required_response_explicit_false(self):
        """Test MFA required response with explicit False."""
        response = auth_schema.MFARequiredRead(mfa_required=False, username="testuser", mfa_challenge="c" * 43)
        assert response.mfa_required is False


class TestAuthRouterErrors:
    """Tests for auth router error responses."""

    @pytest.mark.asyncio
    async def test_login_rejects_partial_pkce_params(self):
        """Test login rejects incomplete PKCE query parameters."""
        endpoint = getattr(
            auth_router.login_for_access_token,
            "__wrapped__",
            auth_router.login_for_access_token,
        )

        with pytest.raises(core_exceptions.DomainError) as exc_info:
            await endpoint(
                response=None,
                request=SimpleNamespace(client=None, headers={}),
                form_data=SimpleNamespace(
                    username="testuser",
                    password="Password1!",
                ),
                client_type="mobile",
                failed_attempts=object(),
                pending_mfa_store=object(),
                password_hasher=object(),
                token_manager=object(),
                db=object(),
                code_challenge="challenge",
                code_challenge_method=None,
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == ("code_challenge and code_challenge_method must be provided together")

    @pytest.mark.asyncio
    async def test_mfa_verify_rejects_partial_pkce_params(self):
        """Test MFA verify rejects incomplete PKCE parameters."""
        endpoint = getattr(
            auth_router.verify_mfa_and_login,
            "__wrapped__",
            auth_router.verify_mfa_and_login,
        )

        with pytest.raises(core_exceptions.DomainError) as exc_info:
            await endpoint(
                response=None,
                request=SimpleNamespace(client=None, headers={}),
                mfa_request=auth_schema.MFALoginRequest(
                    mfa_challenge="c" * 43,
                    mfa_code="123456",
                ),
                client_type="mobile",
                failed_attempts=object(),
                pending_mfa_store=object(),
                password_hasher=object(),
                token_manager=object(),
                db=object(),
                code_challenge=None,
                code_challenge_method="S256",
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == ("code_challenge and code_challenge_method must be provided together")

    @pytest.mark.asyncio
    async def test_invalid_mfa_response_hides_attempt_count(
        self,
        monkeypatch,
    ):
        """Test invalid MFA response does not disclose counters."""
        raw_username = "Raw.User@example.com"
        log_messages = []

        class PendingMFAStore:
            """Minimal pending MFA store for router testing."""

            def is_locked_out(self, username):
                """Return unlocked for test user."""
                return False

            def get_pending_login(self, username):
                """Return a pending login user ID."""
                return 123

            def claim_pending_login(self, username):
                """Return a claimed pending login user ID."""
                return 123

            def record_failed_attempt(self, username):
                """Return a count that must stay server-side only."""
                return 4

        def capture_log(message, *args, **kwargs):
            """Capture warning log messages for assertions."""
            log_messages.append(f"{message} {kwargs.get('extra', {})}")

        monkeypatch.setattr(
            auth_service.mfa_integration,
            "verify_user_mfa",
            lambda *args, **kwargs: False,
        )
        monkeypatch.setattr(
            auth_service.logger,
            "warning",
            capture_log,
        )
        monkeypatch.setattr(
            auth_service.users_integration,
            "get_user",
            lambda *args, **kwargs: SimpleNamespace(id=123, username=raw_username),
        )

        with pytest.raises(core_exceptions.DomainError) as exc_info:
            auth_service.verify_mfa_and_login(
                ip_address="127.0.0.1",
                user_agent="pytest-agent",
                mfa_request=auth_schema.MFALoginRequest(
                    mfa_challenge="c" * 43,
                    mfa_code="123456",
                ),
                client_type="web",
                failed_attempts=object(),
                pending_mfa_store=PendingMFAStore(),
                password_hasher=object(),
                token_manager=object(),
                db=object(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == ("Invalid MFA code, backup code or backup code already used.")
        assert "Failed attempts" not in exc_info.value.detail
        assert raw_username not in " ".join(log_messages)
        assert "username_log_id" in " ".join(log_messages)

    @pytest.mark.asyncio
    async def test_valid_mfa_rejects_already_claimed_pending_login(
        self,
        monkeypatch,
    ):
        """Test valid MFA cannot complete if pending login was claimed."""

        class PendingMFAStore:
            """Minimal pending MFA store for claim testing."""

            def is_locked_out(self, username):
                """Return unlocked for test user."""
                return False

            def get_pending_login(self, username):
                """Return a pending login user ID."""
                return 123

            def claim_pending_login(self, username):
                """Simulate another request already claiming the login."""
                return None

        monkeypatch.setattr(
            auth_service.mfa_integration,
            "verify_user_mfa",
            lambda *args, **kwargs: True,
        )
        monkeypatch.setattr(
            auth_service.users_integration,
            "get_user",
            lambda *args, **kwargs: SimpleNamespace(id=123, username="testuser"),
        )

        with pytest.raises(core_exceptions.DomainError) as exc_info:
            auth_service.verify_mfa_and_login(
                ip_address="127.0.0.1",
                user_agent="pytest-agent",
                mfa_request=auth_schema.MFALoginRequest(
                    mfa_challenge="c" * 43,
                    mfa_code="123456",
                ),
                client_type="web",
                failed_attempts=object(),
                pending_mfa_store=PendingMFAStore(),
                password_hasher=object(),
                token_manager=object(),
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid MFA code, backup code or backup code already used."
