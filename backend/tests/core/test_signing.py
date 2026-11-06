"""Tests for the shared signed-capability-token primitive."""

import time
from unittest.mock import MagicMock, patch

import pytest

import core.http_cache as core_http_cache
import core.key_derivation as core_key_derivation
import core.signing as core_signing


class TestKeyRotation:
    """``SECRET_KEY`` may list several secrets: the first signs, every one verifies."""

    _OLD = "o" * 40
    _NEW = "n" * 40

    @pytest.fixture(autouse=True)
    def _fresh_keys(self):
        core_key_derivation.derive_keys.cache_clear()
        core_signing._serializer.cache_clear()
        yield
        core_key_derivation.derive_keys.cache_clear()
        core_signing._serializer.cache_clear()

    def _with_secret(self, secret: str):
        core_key_derivation.derive_keys.cache_clear()
        core_signing._serializer.cache_clear()
        return patch("core.key_derivation.core_config.read_secret", return_value=secret)

    def test_a_token_signed_with_an_old_listed_key_still_verifies(self):
        with self._with_secret(self._OLD):
            token = core_signing.sign_token("salt", 7)

        with self._with_secret(f"{self._NEW},{self._OLD}"):
            assert core_signing.verify_token("salt", 7, token) is True

    def test_new_tokens_are_signed_with_the_first_key(self):
        with self._with_secret(f"{self._NEW},{self._OLD}"):
            token = core_signing.sign_token("salt", 7)

        with self._with_secret(self._NEW):
            assert core_signing.verify_token("salt", 7, token) is True
        with self._with_secret(self._OLD):
            assert core_signing.verify_token("salt", 7, token) is False

    def test_a_key_that_left_the_list_no_longer_verifies(self):
        with self._with_secret(self._OLD):
            token = core_signing.sign_token("salt", 7)

        with self._with_secret(self._NEW):
            assert core_signing.verify_token("salt", 7, token) is False


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

        signer = core_signing.CapabilitySigner(salt="test-area", max_age_seconds=1, bucket_seconds=1)
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


class TestBlobOrigin:
    @patch("core.signing.core_config")
    def test_local_storage_needs_no_extra_origin(self, mock_config):
        mock_config.settings.resolved_storage_uri = "local://"

        assert core_signing.blob_origin() is None

    @patch("core.signing.platform_runtime")
    @patch("core.signing.core_config")
    def test_object_storage_origin_comes_from_the_presigned_url(self, mock_config, mock_runtime):
        mock_config.settings.resolved_storage_uri = "s3://bucket/prefix"
        storage = MagicMock()
        storage.url.return_value = "https://bucket.s3.eu-west-1.amazonaws.com/prefix/a/k?X-Amz-Signature=s"
        mock_runtime.get_active_platform.return_value.storage = storage

        assert core_signing.blob_origin() == "https://bucket.s3.eu-west-1.amazonaws.com"

    @patch("core.signing.platform_runtime")
    @patch("core.signing.core_config")
    def test_uninitialised_platform_yields_no_origin(self, mock_config, mock_runtime):
        mock_config.settings.resolved_storage_uri = "s3://bucket"
        mock_runtime.get_active_platform.side_effect = RuntimeError("no platform")

        assert core_signing.blob_origin() is None


class TestTokenBuckets:
    """A capability token is the same URL for a while, so the browser cache can hit it."""

    BUCKET = core_signing.DEFAULT_TOKEN_BUCKET_SECONDS
    START = 1_700_000_000 - 1_700_000_000 % BUCKET  # the first second of a bucket

    def _sign_at(self, monkeypatch, now: float, signer: core_signing.CapabilitySigner) -> str:
        monkeypatch.setattr(time, "time", lambda: now)
        return signer.sign(42)

    def test_two_mints_in_one_bucket_are_the_same_token(self, monkeypatch):
        signer = core_signing.CapabilitySigner(salt="bucket-salt")

        first = self._sign_at(monkeypatch, self.START, signer)
        last = self._sign_at(monkeypatch, self.START + self.BUCKET - 1, signer)

        assert first == last

    def test_the_next_bucket_is_a_new_token(self, monkeypatch):
        signer = core_signing.CapabilitySigner(salt="bucket-salt")

        first = self._sign_at(monkeypatch, self.START + self.BUCKET - 1, signer)
        second = self._sign_at(monkeypatch, self.START + self.BUCKET, signer)

        assert first != second

    def test_a_token_is_valid_at_least_the_browser_cache_window_after_any_mint(self, monkeypatch):
        """The worst mint is the last second of a bucket: the stamp is a whole bucket old."""
        signer = core_signing.CapabilitySigner(salt="bucket-salt")
        mint = self.START + self.BUCKET - 1
        token = self._sign_at(monkeypatch, mint, signer)

        monkeypatch.setattr(time, "time", lambda: mint + core_http_cache.SIGNED_URL_CACHE_MAX_AGE)

        assert signer.verify(42, token) is True

    def test_the_cache_window_fits_inside_the_guaranteed_validity(self):
        signer = core_signing.CapabilitySigner(salt="bucket-salt")

        assert signer.max_age_seconds - signer.bucket_seconds >= core_http_cache.SIGNED_URL_CACHE_MAX_AGE

    def test_a_token_never_outlives_the_lifetime_measured_from_its_mint(self, monkeypatch):
        signer = core_signing.CapabilitySigner(salt="bucket-salt")
        mint = self.START + self.BUCKET - 1
        token = self._sign_at(monkeypatch, mint, signer)

        monkeypatch.setattr(time, "time", lambda: mint + signer.max_age_seconds + 1)

        assert signer.verify(42, token) is False

    def test_the_stamp_is_the_start_of_the_bucket(self, monkeypatch):
        signer = core_signing.CapabilitySigner(salt="bucket-salt")
        token = self._sign_at(monkeypatch, self.START + 5, signer)

        monkeypatch.setattr(time, "time", lambda: self.START + signer.max_age_seconds)
        assert signer.verify(42, token) is True
        monkeypatch.setattr(time, "time", lambda: self.START + signer.max_age_seconds + 1)
        assert signer.verify(42, token) is False

    def test_a_bucket_longer_than_the_lifetime_is_refused(self):
        with pytest.raises(ValueError, match="bucket_seconds"):
            core_signing.CapabilitySigner(salt="x", max_age_seconds=60, bucket_seconds=61)

    def test_plain_sign_token_keeps_the_exact_second(self, monkeypatch):
        monkeypatch.setattr(time, "time", lambda: self.START + 5)
        first = core_signing.sign_token("exact-salt", 1)
        monkeypatch.setattr(time, "time", lambda: self.START + 6)

        assert core_signing.sign_token("exact-salt", 1) != first
