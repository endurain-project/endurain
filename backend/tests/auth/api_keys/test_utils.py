"""Tests for auth.api_keys utility functions.

Covers: key generation, HMAC/SHA-256 hashing, scope validation,
and JSON serialisation round-trips.
"""

import hashlib
import json

import pytest

import modules.auth.api_keys.utils as api_keys_utils


class TestGenerateApiKey:
    """Test suite for generate_api_key."""

    def test_starts_with_endurain_prefix(self):
        """Generated keys start with 'endurain_'."""
        key = api_keys_utils.generate_api_key()
        assert key.startswith("endurain_")

    def test_sufficient_entropy(self):
        """Key random part is at least 32 characters long (≥ 256 bits)."""
        key = api_keys_utils.generate_api_key()
        random_part = key[len("endurain_") :]
        # token_urlsafe(32) produces 43 base64url chars
        assert len(random_part) >= 32

    def test_two_keys_are_unique(self):
        """Two independently generated keys are different."""
        assert api_keys_utils.generate_api_key() != api_keys_utils.generate_api_key()


class TestHashApiKey:
    """Test suite for hash_api_key (SHA-256)."""

    def test_returns_64_char_hex_string(self):
        """SHA-256 digest is 64 lowercase hex chars."""
        raw_key = "endurain_sometoken"
        result = api_keys_utils.hash_api_key(raw_key)
        assert len(result) == 64
        assert result == result.lower()

    def test_matches_stdlib_sha256(self):
        """hash_api_key matches a direct hashlib.sha256 call."""
        raw_key = "endurain_knownvalue"
        expected = hashlib.sha256(raw_key.encode()).hexdigest()
        assert api_keys_utils.hash_api_key(raw_key) == expected

    def test_deterministic(self):
        """Same input always produces the same hash."""
        raw_key = "endurain_deterministictest"
        assert api_keys_utils.hash_api_key(raw_key) == api_keys_utils.hash_api_key(raw_key)

    def test_different_inputs_different_hashes(self):
        """Different raw keys produce different hashes."""
        h1 = api_keys_utils.hash_api_key("endurain_aaa")
        h2 = api_keys_utils.hash_api_key("endurain_bbb")
        assert h1 != h2


class TestValidateApiKeyScopes:
    """Test suite for validate_api_key_scopes."""

    def test_valid_scope_passes(self):
        """activities:upload is the only allowed scope and must not raise."""
        api_keys_utils.validate_api_key_scopes(["activities:upload"], "standard")

    def test_unsupported_scope_raises(self):
        """An unsupported scope raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported API key scopes"):
            api_keys_utils.validate_api_key_scopes(["admin:all"], "standard")

    def test_empty_scopes_raises(self):
        """An empty scope list raises ValueError."""
        with pytest.raises(ValueError):
            api_keys_utils.validate_api_key_scopes([], "standard")

    def test_mixed_valid_and_invalid_raises(self):
        """A mix of valid and invalid scopes raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported API key scopes"):
            api_keys_utils.validate_api_key_scopes(["activities:upload", "admin:all"], "standard")

    def test_user_access_type_ignored(self):
        """The _user_access_type argument does not affect scope validation."""
        api_keys_utils.validate_api_key_scopes(["activities:upload"], "premium")
        api_keys_utils.validate_api_key_scopes(["activities:upload"], "free")


class TestScopesJsonRoundTrip:
    """Test suite for scopes_to_json and json_to_scopes."""

    def test_scopes_to_json_produces_valid_json(self):
        """scopes_to_json returns valid JSON string."""
        scopes = ["activities:upload"]
        result = api_keys_utils.scopes_to_json(scopes)
        assert json.loads(result) == scopes

    def test_json_to_scopes_deserialises_correctly(self):
        """json_to_scopes recovers the original list."""
        scopes = ["activities:upload"]
        serialised = json.dumps(scopes)
        assert api_keys_utils.json_to_scopes(serialised) == scopes

    def test_round_trip_is_identity(self):
        """scopes_to_json followed by json_to_scopes is the identity function."""
        scopes = ["activities:upload"]
        assert api_keys_utils.json_to_scopes(api_keys_utils.scopes_to_json(scopes)) == scopes
