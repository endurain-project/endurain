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
    core_key_derivation.derive_key.cache_clear()
    yield
    core_key_derivation.derive_key.cache_clear()


class TestDeriveKey:
    def test_is_an_hmac_of_the_purpose_keyed_by_the_secret(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=_SECRET):
            key = core_key_derivation.derive_key("jwt")

        assert key == hmac.new(_SECRET.encode(), b"endurain:jwt", hashlib.sha256).hexdigest()

    def test_differs_per_purpose_and_from_the_secret(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=_SECRET):
            keys = {core_key_derivation.derive_key(p) for p in ("jwt", "token-hmac", "capability-urls")}

        assert len(keys) == 3
        assert _SECRET not in keys

    def test_is_long_enough_to_key_an_hmac(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=_SECRET):
            assert len(core_key_derivation.derive_key("jwt")) == 64

    def test_follows_the_secret(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=_SECRET):
            first = core_key_derivation.derive_key("jwt")
        core_key_derivation.derive_key.cache_clear()
        with patch("core.key_derivation.core_config.read_secret", return_value="t" * 64):
            second = core_key_derivation.derive_key("jwt")

        assert first != second

    def test_is_none_without_a_secret(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=None):
            assert core_key_derivation.derive_key("jwt") is None


class TestPurposesAreIsolated:
    """No two users of ``SECRET_KEY`` hold the same key."""

    def test_jwt_signing_key_is_not_the_secret(self):
        assert core_config.read_secret("SECRET_KEY") != core_jwt_keys.SIGNING_KEY

    def test_token_hmac_does_not_use_the_jwt_key(self):
        assert access_tokens_integration.hmac_sha256("v") != auth_computation.hmac_sha256(
            "v", core_jwt_keys.SIGNING_KEY
        )

    def test_capability_tokens_do_not_validate_under_the_raw_secret(self):
        token = core_signing.sign_token("salt", 1)

        raw = URLSafeTimedSerializer(core_config.read_secret("SECRET_KEY"), salt="salt")
        with pytest.raises(BadData):
            raw.loads(token)
