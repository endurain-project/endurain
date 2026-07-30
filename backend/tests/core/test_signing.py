"""Tests for the shared signed-capability-token primitive."""

import time

import core.signing as core_signing


class TestSignAndVerifyToken:
    def test_round_trip_is_valid(self):
        token = core_signing.sign_token("test-signing-salt", 42)

        assert core_signing.verify_token("test-signing-salt", 42, token) is True

    def test_rejects_token_bound_to_another_value(self):
        token = core_signing.sign_token("test-signing-salt", 42)

        assert core_signing.verify_token("test-signing-salt", 43, token) is False

    def test_rejects_token_minted_under_another_salt(self):
        """A salt namespaces its tokens: one feature's token must not validate
        under another feature's salt even when both bind the same value."""
        token = core_signing.sign_token("test-signing-salt-a", 1)

        assert core_signing.verify_token("test-signing-salt-b", 1, token) is False

    def test_rejects_forged_token(self):
        assert core_signing.verify_token("test-signing-salt", 42, "totally-made-up-token") is False

    def test_rejects_malformed_token_without_raising(self):
        # Malformed base64/payload (BadData, not just BadSignature) must be
        # swallowed to a False rather than propagating on untrusted input.
        assert core_signing.verify_token("test-signing-salt", 1, "a.b.c.d") is False
        assert core_signing.verify_token("test-signing-salt", 1, "") is False

    def test_token_is_urlsafe_and_nonempty(self):
        token = core_signing.sign_token("test-signing-salt", 1)

        assert token
        assert " " not in token


class TestTokenExpiry:
    def test_max_age_none_never_expires(self):
        """Omitting max_age preserves the original no-expiry behaviour."""
        token = core_signing.sign_token("test-signing-expiry-salt", 1)
        time.sleep(1.1)

        assert core_signing.verify_token("test-signing-expiry-salt", 1, token) is True

    def test_token_within_max_age_is_valid(self):
        token = core_signing.sign_token("test-signing-expiry-salt", 1)

        assert core_signing.verify_token("test-signing-expiry-salt", 1, token, max_age=60) is True

    def test_token_older_than_max_age_is_rejected(self):
        token = core_signing.sign_token("test-signing-expiry-salt", 1)
        time.sleep(2.1)

        assert core_signing.verify_token("test-signing-expiry-salt", 1, token, max_age=1) is False
