"""A session stores a keyed digest of its refresh token, not a slow password hash, and survives a key rotation."""

import pytest

import core.key_derivation as core_key_derivation
import modules.auth.sessions.integration_service as sessions_integration

_TOKEN = "header.payload.signature"


@pytest.fixture
def secret_key(monkeypatch):
    """Return a function that makes the server's ``SECRET_KEY`` list the given one, as a rotation does."""

    read_secret = core_key_derivation.core_config.read_secret

    def use(secret: str) -> None:
        core_key_derivation.derive_keys.cache_clear()
        monkeypatch.setattr(
            core_key_derivation.core_config,
            "read_secret",
            lambda name, default_value=None: secret if name == "SECRET_KEY" else read_secret(name, default_value),
        )

    yield use
    core_key_derivation.derive_keys.cache_clear()


def test_the_stored_value_is_a_hex_digest_that_is_not_the_token():
    stored = sessions_integration.hash_refresh_token(_TOKEN)

    assert stored != _TOKEN
    assert len(stored) == 64
    assert int(stored, 16) >= 0
    assert not stored.startswith("$argon2")


def test_the_digest_of_a_token_is_stable():
    assert sessions_integration.hash_refresh_token(_TOKEN) == sessions_integration.hash_refresh_token(_TOKEN)


def test_the_presented_token_matches_its_digest_and_no_other_token_does():
    stored = sessions_integration.hash_refresh_token(_TOKEN)

    assert sessions_integration.verify_refresh_token(_TOKEN, stored)
    assert not sessions_integration.verify_refresh_token(_TOKEN + "x", stored)
    assert not sessions_integration.verify_refresh_token("", stored)


def test_an_argon2_hash_stored_before_the_change_never_matches():
    legacy = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaGhhc2hoYXNoaGFzaA"

    assert not sessions_integration.verify_refresh_token(_TOKEN, legacy)


class TestKeyRotation:
    """A digest stored under the old ``SECRET_KEY`` still verifies once the key list is ``new,old``."""

    def test_a_digest_made_under_the_old_key_verifies_once_the_old_key_is_listed_second(self, secret_key):
        secret_key("o" * 40)
        stored = sessions_integration.hash_refresh_token("token")

        secret_key(f"{'n' * 40},{'o' * 40}")

        assert sessions_integration.verify_refresh_token("token", stored) is True
        assert sessions_integration.verify_refresh_token("other", stored) is False

    def test_a_digest_made_under_a_key_that_left_the_list_does_not_verify(self, secret_key):
        secret_key("o" * 40)
        stored = sessions_integration.hash_refresh_token("token")

        secret_key("n" * 40)

        assert sessions_integration.verify_refresh_token("token", stored) is False

    def test_new_digests_use_the_first_key(self, secret_key):
        secret_key(f"{'n' * 40},{'o' * 40}")
        stored = sessions_integration.hash_refresh_token("token")

        secret_key("n" * 40)

        assert sessions_integration.verify_refresh_token("token", stored) is True
