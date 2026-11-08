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
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.service as auth_service
from tests._helpers.auth import pending_login


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

    def test_mfa_login_request_invalid_code_non_ascii_digits(self):
        """Test MFA login request with digits outside ASCII."""
        with pytest.raises(ValidationError) as exc_info:
            auth_schema.MFALoginRequest(mfa_challenge="c" * 43, mfa_code="\u0661\u0662\u0663\u0664\u0665\u0666")
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

    def test_mfa_required_response_names_the_next_step(self):
        """The body holds the step and the challenge only."""
        response = auth_schema.MFARequiredRead(next_step="mfa", mfa_challenge="c" * 43)

        assert response.model_dump() == {"next_step": "mfa", "mfa_challenge": "c" * 43}

    def test_mfa_required_response_requires_the_next_step(self):
        """A body without the step is refused rather than defaulted."""
        with pytest.raises(ValueError, match="next_step"):
            auth_schema.MFARequiredRead.model_validate({"mfa_challenge": "c" * 43})

    def test_mfa_required_response_refuses_another_step(self):
        """The step is the literal ``mfa``."""
        with pytest.raises(ValueError, match="next_step"):
            auth_schema.MFARequiredRead(next_step="tokens", mfa_challenge="c" * 43)


class TestAuthRouterErrors:
    """Tests for auth router error responses."""

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
                """Return a pending login."""
                return pending_login(123)

            def claim_pending_login(self, username):
                """Return a claimed pending login."""
                return pending_login(123)

            def record_failed_attempt(self, username):
                """Return a count that must stay server-side only."""
                return 4

            def record_wrong_code(self, challenge):
                """Leave the challenge live."""
                return False

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
                password_change_store=MagicMock(),
                device_id=None,
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
        """Test valid MFA cannot complete if pending login was claimed; the challenge is dead, so the answer is 401."""

        class PendingMFAStore:
            """Minimal pending MFA store for claim testing."""

            def is_locked_out(self, username):
                """Return unlocked for test user."""
                return False

            def get_pending_login(self, username):
                """Return a pending login."""
                return pending_login(123)

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
                password_change_store=MagicMock(),
                device_id=None,
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Unable to authenticate with provided credentials"
