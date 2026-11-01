"""Tests for the SSO token-exchange schemas."""

import pytest
from pydantic import ValidationError

from modules.auth.authentication.schema import TokenExchangeRead, TokenExchangeRequest


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


class TestTokenExchangeRead:
    """Test suite for TokenExchangeRead schema."""

    def test_valid_token_exchange_response(self):
        """Test creating a valid TokenExchangeRead instance.

        Asserts:
            - Instance is created successfully with all required fields
            - Default values are applied
        """
        # Arrange & Act
        response = TokenExchangeRead(
            session_id="session-123",
            access_token="access-token-xyz",
            refresh_token="refresh-token-abc",
            csrf_token="csrf-token-def",
        )

        # Assert
        assert response.session_id == "session-123"
        assert response.access_token == "access-token-xyz"
        assert response.refresh_token == "refresh-token-abc"
        assert response.csrf_token == "csrf-token-def"
        assert response.expires_in == 900  # Default value
        assert response.token_type == "Bearer"  # Default value

    def test_token_exchange_response_required_fields(self):
        """Test required fields for TokenExchangeRead.

        Asserts:
            - ValidationError is raised when required fields are missing
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            TokenExchangeRead()

        error_str = str(exc_info.value)
        assert "session_id" in error_str or "access_token" in error_str

    def test_token_exchange_response_custom_expires_in(self):
        """Test custom expires_in value for TokenExchangeRead.

        Asserts:
            - Custom expires_in value can be set
        """
        # Arrange & Act
        response = TokenExchangeRead(
            session_id="session-123",
            access_token="access-token-xyz",
            refresh_token="refresh-token-abc",
            csrf_token="csrf-token-def",
            expires_in=1800,
        )

        # Assert
        assert response.expires_in == 1800

    def test_token_exchange_response_custom_token_type(self):
        """Test custom token_type value for TokenExchangeRead.

        Asserts:
            - Custom token_type value can be set
        """
        # Arrange & Act
        response = TokenExchangeRead(
            session_id="session-123",
            access_token="access-token-xyz",
            refresh_token="refresh-token-abc",
            csrf_token="csrf-token-def",
            token_type="Custom",
        )

        # Assert
        assert response.token_type == "Custom"
