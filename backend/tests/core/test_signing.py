"""Tests for the shared signed-capability-token primitive."""

import time
from unittest.mock import MagicMock, patch

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


class TestCapabilitySigner:
    """The salt and its lifetime travel together, so a verify cannot drop the age."""

    def test_round_trip_is_valid(self):
        import core.signing as core_signing

        signer = core_signing.CapabilitySigner(salt="test-area")

        assert signer.verify(42, signer.sign(42)) is True

    def test_rejects_a_token_bound_to_another_value(self):
        import core.signing as core_signing

        signer = core_signing.CapabilitySigner(salt="test-area")

        assert signer.verify(43, signer.sign(42)) is False

    def test_a_token_from_another_salt_does_not_validate(self):
        """Salts namespace the families, so ids cannot be replayed across features."""
        import core.signing as core_signing

        a = core_signing.CapabilitySigner(salt="area-a")
        b = core_signing.CapabilitySigner(salt="area-b")

        assert b.verify(42, a.sign(42)) is False

    def test_an_expired_token_is_rejected(self):
        import time

        import core.signing as core_signing

        signer = core_signing.CapabilitySigner(salt="test-area", max_age_seconds=1)
        token = signer.sign(42)
        time.sleep(2.1)

        assert signer.verify(42, token) is False

    def test_the_default_lifetime_is_bounded(self):
        """Not eternal: a token must stop outliving the decision it was minted from."""
        import core.signing as core_signing

        assert 0 < core_signing.CapabilitySigner(salt="x").max_age_seconds <= 24 * 60 * 60


class TestBlobUrl:
    @patch("core.signing.core_config")
    def test_local_storage_uses_the_token_gated_route(self, mock_config):
        import core.signing as core_signing

        mock_config.settings.resolved_storage_uri = "local://data"
        mock_config.ROOT_PATH = "/api/v1"

        url = core_signing.blob_url("area", "k.webp", local_path="/things/1/blob", token="tok")

        assert url == "/api/v1/things/1/blob?t=tok"

    @patch("core.signing.platform_runtime")
    @patch("core.signing.core_config")
    def test_object_storage_uses_its_presigned_url(self, mock_config, mock_runtime):
        import core.signing as core_signing

        mock_config.settings.resolved_storage_uri = "s3://bucket"
        storage = MagicMock()
        storage.url.return_value = "https://cdn/area/k.webp"
        mock_runtime.get_active_platform.return_value.storage = storage

        url = core_signing.blob_url("area", "k.webp", local_path="/things/1/blob", token="tok")

        assert url == "https://cdn/area/k.webp"
        storage.url.assert_called_once_with("area", "k.webp")

    @patch("core.signing.platform_runtime")
    @patch("core.signing.core_config")
    def test_falls_back_to_the_route_when_the_platform_is_uninitialised(self, mock_config, mock_runtime):
        """Serialization must still work outside a running app (tests, migrations)."""
        import core.signing as core_signing

        mock_config.settings.resolved_storage_uri = "s3://bucket"
        mock_config.ROOT_PATH = "/api/v1"
        mock_runtime.get_active_platform.side_effect = RuntimeError("no platform")

        url = core_signing.blob_url("area", "k.webp", local_path="/things/1/blob", token="tok")

        assert url == "/api/v1/things/1/blob?t=tok"
