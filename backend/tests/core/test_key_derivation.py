"""Tests for the per-purpose keys derived from the server ``SECRET_KEY``."""

import hashlib
import hmac
from unittest.mock import patch

import pytest
from itsdangerous import BadData, URLSafeTimedSerializer

import core.config as core_config
import core.jwt_keys as core_jwt_keys
import core.key_derivation as core_key_derivation
import core.signing as core_signing
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.computation as auth_computation

_SECRET = "s" * 64


@pytest.fixture(autouse=True)
def _fresh_cache():
    core_key_derivation.derive_keys.cache_clear()
    yield
    core_key_derivation.derive_keys.cache_clear()


class TestDeriveKey:
    def test_is_an_hmac_of_the_purpose_keyed_by_the_secret(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=_SECRET):
            key = core_key_derivation.derive_key("jwt")

        assert key == hmac.new(_SECRET.encode(), b"endurain:jwt", hashlib.sha256).hexdigest()

    def test_differs_per_purpose_and_from_the_secret(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=_SECRET):
            keys = {
                core_key_derivation.derive_key(p)
                for p in ("jwt", "refresh-jwt", "token-hmac", "email-token", "capability-urls")
            }

        assert len(keys) == 5
        assert _SECRET not in keys

    def test_is_long_enough_to_key_an_hmac(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=_SECRET):
            assert len(core_key_derivation.derive_key("jwt")) == 64

    def test_follows_the_secret(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=_SECRET):
            first = core_key_derivation.derive_key("jwt")
        core_key_derivation.derive_keys.cache_clear()
        with patch("core.key_derivation.core_config.read_secret", return_value="t" * 64):
            second = core_key_derivation.derive_key("jwt")

        assert first != second

    def test_is_none_without_a_secret(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=None):
            assert core_key_derivation.derive_key("jwt") is None


class TestKeyList:
    """``SECRET_KEY`` may list several secrets: the first signs, every one verifies."""

    def test_a_list_derives_one_key_per_secret_in_order(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=f"{_SECRET},{'t' * 64}"):
            keys = core_key_derivation.derive_keys("jwt")

        assert keys == tuple(
            hmac.new(secret.encode(), b"endurain:jwt", hashlib.sha256).hexdigest() for secret in (_SECRET, "t" * 64)
        )

    def test_the_single_key_is_the_first(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=f"{_SECRET},{'t' * 64}"):
            assert core_key_derivation.derive_key("jwt") == core_key_derivation.derive_keys("jwt")[0]

    def test_a_single_secret_is_a_list_of_one(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=_SECRET):
            assert len(core_key_derivation.derive_keys("jwt")) == 1

    def test_whitespace_around_an_entry_is_dropped(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=f" {_SECRET} , {'t' * 64} "):
            keys = core_key_derivation.derive_keys("jwt")
        core_key_derivation.derive_keys.cache_clear()
        with patch("core.key_derivation.core_config.read_secret", return_value=f"{_SECRET},{'t' * 64}"):
            assert keys == core_key_derivation.derive_keys("jwt")

    def test_an_empty_entry_is_refused(self):
        with (
            patch("core.key_derivation.core_config.read_secret", return_value=f"{_SECRET},"),
            pytest.raises(ValueError, match="SECRET_KEY contains an empty entry"),
        ):
            core_key_derivation.derive_keys("jwt")

    def test_no_secret_is_no_keys(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=None):
            assert core_key_derivation.derive_keys("jwt") == ()


class TestPurposesAreIsolated:
    """No two users of ``SECRET_KEY`` hold the same key."""

    def test_jwt_signing_key_is_not_the_secret(self):
        assert core_config.read_secret("SECRET_KEY") != core_jwt_keys.SIGNING_KEYS[0]

    def test_refresh_tokens_are_not_signed_with_the_access_token_key(self):
        assert core_key_derivation.REFRESH_JWT == "refresh-jwt"
        assert core_jwt_keys.REFRESH_SIGNING_KEYS[0] != core_jwt_keys.SIGNING_KEYS[0]

    def test_token_hmac_does_not_use_the_jwt_key(self):
        assert access_tokens_integration.hmac_sha256("v") != auth_computation.hmac_sha256(
            "v", core_jwt_keys.SIGNING_KEYS[0]
        )

    def test_the_email_token_key_is_not_the_token_digest_key(self):
        assert core_key_derivation.derive_key(core_key_derivation.EMAIL_TOKEN) != core_key_derivation.derive_key(
            core_key_derivation.TOKEN_HMAC
        )

    def test_a_raw_emailed_token_is_not_the_token_digest_value(self):
        assert access_tokens_integration.derive_email_token(
            "password-reset:e"
        ) != access_tokens_integration.hmac_sha256("password-reset:e")

    def test_capability_tokens_do_not_validate_under_the_raw_secret(self):
        token = core_signing.sign_token("salt", 1)

        raw = URLSafeTimedSerializer(core_config.read_secret("SECRET_KEY"), salt="salt")
        with pytest.raises(BadData):
            raw.loads(token)
