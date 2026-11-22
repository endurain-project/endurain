"""A session stores a keyed digest of its refresh token, not a slow password hash."""

from unittest.mock import patch

import modules.auth.sessions.integration_service as sessions_integration

_TOKEN = "header.payload.signature"


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


def test_a_digest_stored_under_an_older_secret_key_still_matches():
    older = "a" * 64
    newer = "b" * 64
    with patch(
        "modules.auth.sessions.service.access_tokens_integration.hmac_sha256_under_every_key",
        return_value=(newer, older),
    ):
        assert sessions_integration.verify_refresh_token(_TOKEN, older)
        assert not sessions_integration.verify_refresh_token(_TOKEN, "c" * 64)


def test_an_argon2_hash_stored_before_the_change_never_matches():
    legacy = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaGhhc2hoYXNoaGFzaA"

    assert not sessions_integration.verify_refresh_token(_TOKEN, legacy)
