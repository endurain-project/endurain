"""Tests for auth.computation.

token_hashing centralizes the two token-hashing strategies used across the
auth token modules:

- :func:`sha256_hex` — plain SHA-256, for high-entropy single-purpose opaque
  tokens (API keys, password-reset, sign-up, IdP link tokens).
- :func:`hmac_sha256` — keyed HMAC-SHA256 using a supplied secret, for
  refresh-token reuse detection and CSRF tokens (defense-in-depth: unforgeable
  without the server secret).

Both must be deterministic, lowercase, 64-char hex digests to support indexed
equality lookups. These tests assert those security-relevant properties using
real hashing (no mocks of the crypto itself).
"""

import hashlib
import hmac
import re

import pytest

import core.exceptions as core_exceptions
import modules.auth.computation as token_hashing
from modules.auth.computation import _secure_compare, validate_pkce_verifier

_HEX_RE = r"^[0-9a-f]{64}$"


class TestSha256Hex:
    """sha256_hex: plain SHA-256 hex digest."""

    def test_matches_hashlib_reference(self):
        value = "high-entropy-token-value"
        expected = hashlib.sha256(value.encode()).hexdigest()
        assert token_hashing.sha256_hex(value) == expected

    def test_is_deterministic(self):
        value = "repeatable"
        assert token_hashing.sha256_hex(value) == token_hashing.sha256_hex(value)

    def test_output_is_lowercase_64_char_hex(self):
        digest = token_hashing.sha256_hex("anything")
        assert re.match(_HEX_RE, digest), "must be 64-char lowercase hex"

    def test_distinct_inputs_produce_distinct_digests(self):
        assert token_hashing.sha256_hex("token-a") != token_hashing.sha256_hex("token-b")

    def test_empty_string_hashes(self):
        expected = hashlib.sha256(b"").hexdigest()
        assert token_hashing.sha256_hex("") == expected

    def test_accepts_bytes_and_agrees_with_the_utf8_string(self):
        assert token_hashing.sha256_hex(b"payload") == token_hashing.sha256_hex("payload")


class TestHmacSha256:
    """hmac_sha256: keyed HMAC-SHA256 using a supplied secret."""

    def test_matches_hmac_reference(self):
        key = "test-secret-key-for-testing-only-min-32-chars"
        value = "refresh-token-value"
        expected = hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()
        assert token_hashing.hmac_sha256(value, key) == expected

    def test_is_deterministic_for_same_key_and_value(self):
        key = "a-secret-key-1234567890-1234567890"
        first = token_hashing.hmac_sha256("value", key)
        second = token_hashing.hmac_sha256("value", key)
        assert first == second

    def test_output_is_lowercase_64_char_hex(self):
        digest = token_hashing.hmac_sha256("value", "a-secret-key-1234567890-1234567890")
        assert re.match(_HEX_RE, digest), "must be 64-char lowercase hex"

    def test_different_keys_produce_different_digests(self):
        value = "same-value"
        with_key_one = token_hashing.hmac_sha256(value, "key-one-1234567890-1234567890-12")
        with_key_two = token_hashing.hmac_sha256(value, "key-two-1234567890-1234567890-12")
        assert with_key_one != with_key_two

    def test_keyed_digest_differs_from_plain_sha256(self):
        """The HMAC of a value must not equal its plain SHA-256 digest."""
        value = "csrf-token"
        keyed = token_hashing.hmac_sha256(value, "a-secret-key-1234567890-1234567890")
        assert keyed != token_hashing.sha256_hex(value)

    def test_empty_secret_key_raises_value_error(self):
        with pytest.raises(ValueError, match="secret_key must not be empty"):
            token_hashing.hmac_sha256("value", "")


class TestValidatePkceVerifier:
    """Test suite for validate_pkce_verifier function."""

    def test_validate_pkce_verifier_success(self):
        """Test validating a valid PKCE verifier.

        Asserts:
            - Valid verifier that matches challenge passes validation
        """
        # Arrange
        # Valid verifier (RFC 7636 compliant)
        code_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        # Corresponding S256 challenge
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        code_challenge_method = "S256"

        # Act & Assert (no exception should be raised)
        validate_pkce_verifier(code_verifier, code_challenge, code_challenge_method)

    def test_validate_pkce_verifier_min_length_violation(self):
        """Test PKCE verifier minimum length validation.

        Asserts:
            - HTTPException is raised for verifier shorter than 43 chars
        """
        # Arrange
        code_verifier = "a" * 42  # Too short
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        code_challenge_method = "S256"

        # Act & Assert
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_pkce_verifier(code_verifier, code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "43-128 characters" in str(exc_info.value.detail)

    def test_validate_pkce_verifier_max_length_violation(self):
        """Test PKCE verifier maximum length validation.

        Asserts:
            - HTTPException is raised for verifier longer than 128 chars
        """
        # Arrange
        code_verifier = "a" * 129  # Too long
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        code_challenge_method = "S256"

        # Act & Assert
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_pkce_verifier(code_verifier, code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "43-128 characters" in str(exc_info.value.detail)

    def test_validate_pkce_verifier_invalid_characters(self):
        """Test PKCE verifier with invalid characters.

        Asserts:
            - HTTPException is raised for non-base64url characters
        """
        # Arrange
        code_verifier = "a" * 43 + "!@#"  # Invalid characters
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        code_challenge_method = "S256"

        # Act & Assert
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_pkce_verifier(code_verifier, code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "valid base64url" in str(exc_info.value.detail)

    def test_validate_pkce_verifier_wrong_method(self):
        """Test PKCE verifier with wrong challenge method.

        Asserts:
            - HTTPException is raised for non-S256 method
        """
        # Arrange
        code_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        code_challenge_method = "plain"

        # Act & Assert
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_pkce_verifier(code_verifier, code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "Only S256 PKCE method is supported" in str(exc_info.value.detail)

    def test_validate_pkce_verifier_mismatch(self):
        """Test PKCE verifier that doesn't match challenge.

        Asserts:
            - HTTPException is raised for mismatched verifier
        """
        # Arrange
        code_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        code_challenge = "wrong_challenge_value_that_does_not_match_verifier"
        code_challenge_method = "S256"

        # Act & Assert
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_pkce_verifier(code_verifier, code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "Invalid code_verifier" in str(exc_info.value.detail)


class TestSecureCompare:
    """Test suite for _secure_compare function."""

    def test_secure_compare_equal_strings(self):
        """Test secure comparison of equal strings.

        Asserts:
            - Returns True for identical strings
        """
        # Arrange
        str1 = "test_string_123"
        str2 = "test_string_123"

        # Act
        result = _secure_compare(str1, str2)

        # Assert
        assert result is True

    def test_secure_compare_different_strings(self):
        """Test secure comparison of different strings.

        Asserts:
            - Returns False for different strings
        """
        # Arrange
        str1 = "test_string_123"
        str2 = "test_string_456"

        # Act
        result = _secure_compare(str1, str2)

        # Assert
        assert result is False

    def test_secure_compare_different_lengths(self):
        """Test secure comparison of strings with different lengths.

        Asserts:
            - Returns False for strings of different lengths
        """
        # Arrange
        str1 = "short"
        str2 = "much_longer_string"

        # Act
        result = _secure_compare(str1, str2)

        # Assert
        assert result is False

    def test_secure_compare_empty_strings(self):
        """Test secure comparison of empty strings.

        Asserts:
            - Returns True for both empty strings
        """
        # Arrange
        str1 = ""
        str2 = ""

        # Act
        result = _secure_compare(str1, str2)

        # Assert
        assert result is True

    def test_secure_compare_one_empty_string(self):
        """Test secure comparison with one empty string.

        Asserts:
            - Returns False when one string is empty
        """
        # Arrange
        str1 = "non_empty"
        str2 = ""

        # Act
        result = _secure_compare(str1, str2)

        # Assert
        assert result is False

    def test_secure_compare_case_sensitive(self):
        """Test secure comparison is case-sensitive.

        Asserts:
            - Returns False for strings differing only in case
        """
        # Arrange
        str1 = "TestString"
        str2 = "teststring"

        # Act
        result = _secure_compare(str1, str2)

        # Assert
        assert result is False
