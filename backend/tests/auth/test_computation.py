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

import modules.auth.computation as token_hashing

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
