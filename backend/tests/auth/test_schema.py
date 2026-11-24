"""
Tests for auth.schema module and auth router error responses.

Store behaviour (login/MFA/step-up lockout) is covered in
``tests/auth/lockout/test_lockout.py``; this module keeps the Pydantic schema
tests and the router-level error-path tests.
"""

import uuid

import pytest
from pydantic import ValidationError

import modules.auth.authentication.schema as auth_schema

_USER_ID = uuid.UUID(int=123)


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
        """The body holds the step, the challenge and the methods the account can answer with."""
        response = auth_schema.MFARequiredRead(next_step="mfa", mfa_challenge="c" * 43, methods=["totp", "backup_code"])

        assert response.model_dump() == {
            "next_step": "mfa",
            "mfa_challenge": "c" * 43,
            "methods": ["totp", "backup_code"],
        }

    def test_mfa_required_response_requires_the_methods(self):
        """The methods are stated, never defaulted."""
        with pytest.raises(ValueError, match="methods"):
            auth_schema.MFARequiredRead.model_validate({"next_step": "mfa", "mfa_challenge": "c" * 43})

    def test_mfa_required_response_requires_the_next_step(self):
        """A body without the step is refused rather than defaulted."""
        with pytest.raises(ValueError, match="next_step"):
            auth_schema.MFARequiredRead.model_validate({"mfa_challenge": "c" * 43, "methods": []})

    def test_mfa_required_response_refuses_another_step(self):
        """The step is the literal ``mfa``."""
        with pytest.raises(ValueError, match="next_step"):
            auth_schema.MFARequiredRead(next_step="tokens", mfa_challenge="c" * 43, methods=[])
