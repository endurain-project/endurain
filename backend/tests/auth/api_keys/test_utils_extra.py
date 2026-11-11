"""Tests for users_api_keys utility functions."""

import modules.auth.api_keys.constants as auth_api_keys_constants
import modules.auth.api_keys.utils as auth_api_keys_utils


class TestGenerateApiKey:
    """
    Test suite for generate_api_key function.
    """

    def test_generate_api_key_starts_with_prefix(self):
        """Test that generated key starts with the 'endurain_' prefix."""
        key = auth_api_keys_utils.generate_api_key()
        assert key.startswith("endurain_")

    def test_generate_api_key_length(self):
        """Test that generated key has expected minimum length."""
        key = auth_api_keys_utils.generate_api_key()
        # "endurain_" (9 chars) + token_urlsafe(32) is at least 43 chars
        assert len(key) > 9

    def test_generate_api_key_uniqueness(self):
        """Test that two generated keys are different (high-entropy enforcement)."""
        key1 = auth_api_keys_utils.generate_api_key()
        key2 = auth_api_keys_utils.generate_api_key()
        assert key1 != key2

    def test_generate_api_key_random_part_length(self):
        """Test that the random part has at least 40 characters (base64url of 32 bytes)."""
        key = auth_api_keys_utils.generate_api_key()
        random_part = key[len("endurain_") :]
        assert len(random_part) >= 40


class TestHashApiKey:
    """
    Test suite for hash_api_key function.
    """

    def test_hash_api_key_returns_64_hex_chars(self):
        """Test that SHA-256 digest is 64 hexadecimal characters."""
        digest = auth_api_keys_utils.hash_api_key("endurain_sometoken")
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_hash_api_key_deterministic(self):
        """Test that the same input always produces the same hash."""
        raw_key = "endurain_testinput"
        digest1 = auth_api_keys_utils.hash_api_key(raw_key)
        digest2 = auth_api_keys_utils.hash_api_key(raw_key)
        assert digest1 == digest2

    def test_hash_api_key_different_inputs(self):
        """Test that different inputs produce different hashes."""
        digest1 = auth_api_keys_utils.hash_api_key("endurain_keyA")
        digest2 = auth_api_keys_utils.hash_api_key("endurain_keyB")
        assert digest1 != digest2

    def test_hash_api_key_known_value(self):
        """Test hash against a known SHA-256 value for correctness."""
        import hashlib

        raw = "endurain_known_test_value"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert auth_api_keys_utils.hash_api_key(raw) == expected


class TestApiKeyScopesAreStoredByName:
    """A key's scopes are stored as their names, so a stored key reads back the same strings."""

    def test_scope_members_are_stored_as_their_values(self):
        scopes = [auth_api_keys_constants.ApiKeyScope.GEARS_READ, auth_api_keys_constants.ApiKeyScope.ACCOUNT]

        stored = auth_api_keys_utils.scopes_to_json(scopes)

        assert stored == '["gears:read", "account"]'
        assert auth_api_keys_utils.json_to_scopes(stored) == ["gears:read", "account"]


class TestScopesJsonRoundTrip:
    """
    Test suite for scopes_to_json and json_to_scopes functions.
    """

    def test_scopes_to_json_returns_string(self):
        """Test that scopes_to_json returns a string."""
        result = auth_api_keys_utils.scopes_to_json(["activities:upload"])
        assert isinstance(result, str)

    def test_scopes_to_json_serialises_list(self):
        """Test that scopes_to_json correctly serialises a list."""
        scopes = ["activities:read", "activities:upload"]
        result = auth_api_keys_utils.scopes_to_json(scopes)
        assert "activities:read" in result
        assert "activities:upload" in result

    def test_json_to_scopes_returns_list(self):
        """Test that json_to_scopes returns a list."""
        result = auth_api_keys_utils.json_to_scopes('["activities:upload"]')
        assert isinstance(result, list)

    def test_scopes_round_trip(self):
        """Test that serialising and deserialising scopes produces the same list."""
        original = ["activities:read", "activities:upload", "gears:read"]
        serialised = auth_api_keys_utils.scopes_to_json(original)
        deserialised = auth_api_keys_utils.json_to_scopes(serialised)
        assert deserialised == original

    def test_scopes_to_json_empty_list(self):
        """Test that an empty list serialises and deserialises correctly."""
        serialised = auth_api_keys_utils.scopes_to_json([])
        deserialised = auth_api_keys_utils.json_to_scopes(serialised)
        assert deserialised == []
