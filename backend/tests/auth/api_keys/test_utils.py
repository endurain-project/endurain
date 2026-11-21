"""API-key generation, hashing and scope encoding."""

import hashlib

import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.utils as api_keys_utils


class TestGenerateApiKey:
    def test_a_key_is_the_prefix_and_a_256_bit_url_safe_token(self):
        key = api_keys_utils.generate_api_key()

        assert key.startswith("endurain_")
        assert len(key) == len("endurain_") + 43

    def test_two_keys_differ(self):
        assert api_keys_utils.generate_api_key() != api_keys_utils.generate_api_key()


class TestHashApiKey:
    def test_the_hash_is_the_sha256_hex_digest(self):
        raw = "endurain_known_test_value"

        digest = api_keys_utils.hash_api_key(raw)

        assert digest == hashlib.sha256(raw.encode()).hexdigest()
        assert len(digest) == 64

    def test_the_same_key_hashes_alike_and_different_keys_differ(self):
        assert api_keys_utils.hash_api_key("endurain_keyA") == api_keys_utils.hash_api_key("endurain_keyA")
        assert api_keys_utils.hash_api_key("endurain_keyA") != api_keys_utils.hash_api_key("endurain_keyB")


class TestScopes:
    def test_scope_members_are_stored_as_their_values_and_read_back_as_strings(self):
        scopes = [api_keys_constants.ApiKeyScope.GEARS_READ, api_keys_constants.ApiKeyScope.ACCOUNT]

        stored = api_keys_utils.scopes_to_json(scopes)

        assert stored == '["gears:read", "account"]'
        assert api_keys_utils.json_to_scopes(stored) == ["gears:read", "account"]

    def test_an_empty_scope_list_round_trips(self):
        assert api_keys_utils.json_to_scopes(api_keys_utils.scopes_to_json([])) == []
