"""Tests for the SSO token-exchange schemas."""

import pytest
from pydantic import ValidationError

from modules.auth.authentication.schema import TokenExchangeRequest


class TestTokenExchangeRequest:
    """Test suite for TokenExchangeRequest schema."""

    def test_valid_token_exchange_request(self):
        """Test creating a valid TokenExchangeRequest instance.

        Asserts:
            - Instance is created successfully with valid code_verifier
        """
        # Arrange
        # Valid base64url string (43 characters minimum)
        code_verifier = "a" * 43 + "B1-_" * 10

        # Act
        request = TokenExchangeRequest(code_verifier=code_verifier)

        # Assert
        assert request.code_verifier == code_verifier

    def test_mfa_code_rejects_non_ascii_digits(self):
        """Test mfa_code rejects digits outside ASCII.

        Asserts:
            - ValidationError is raised for a 6-digit code in Arabic-Indic digits
        """
        with pytest.raises(ValidationError) as exc_info:
            TokenExchangeRequest(code_verifier="a" * 43, mfa_code="\u0661\u0662\u0663\u0664\u0665\u0666")

        assert "mfa_code" in str(exc_info.value)

    def test_code_verifier_min_length(self):
        """Test code_verifier minimum length validation.

        Asserts:
            - ValidationError is raised when code_verifier is less than 43 chars
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            TokenExchangeRequest(code_verifier="a" * 42)

        assert "String should have at least 43 characters" in str(exc_info.value)

    def test_code_verifier_max_length(self):
        """Test code_verifier maximum length validation.

        Asserts:
            - ValidationError is raised when code_verifier exceeds 128 chars
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            TokenExchangeRequest(code_verifier="a" * 129)

        assert "String should have at most 128 characters" in str(exc_info.value)

    def test_code_verifier_format_validation_valid(self):
        """Test code_verifier format validation accepts valid base64url.

        Asserts:
            - Valid base64url characters (A-Z, a-z, 0-9, -, _) are accepted
        """
        # Arrange
        valid_verifier = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

        # Act
        request = TokenExchangeRequest(code_verifier=valid_verifier)

        # Assert
        assert request.code_verifier == valid_verifier

    def test_code_verifier_format_validation_invalid(self):
        """Test code_verifier format validation rejects invalid characters.

        Asserts:
            - ValidationError is raised for non-base64url characters
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            TokenExchangeRequest(code_verifier="a" * 43 + "!")  # ! is not valid base64url

        assert "code_verifier must be valid base64url" in str(exc_info.value)

    def test_code_verifier_format_validation_special_chars(self):
        """Test code_verifier format validation rejects special characters.

        Asserts:
            - ValidationError is raised for special characters like +, =
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            TokenExchangeRequest(code_verifier="a" * 43 + "+")

        assert "code_verifier must be valid base64url" in str(exc_info.value)
