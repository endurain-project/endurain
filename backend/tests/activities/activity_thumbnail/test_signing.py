"""Tests for thumbnail addressing: storage keys, signed tokens, and servable URLs."""

from unittest.mock import MagicMock, patch


class TestThumbnailTokenSigning:
    def test_round_trip_is_valid(self):
        from modules.activities.activity_thumbnail.signing import (
            sign_thumbnail_token,
            verify_thumbnail_token,
        )

        token = sign_thumbnail_token(42)

        assert verify_thumbnail_token(42, token) is True

    def test_rejects_token_bound_to_another_activity(self):
        from modules.activities.activity_thumbnail.signing import (
            sign_thumbnail_token,
            verify_thumbnail_token,
        )

        token = sign_thumbnail_token(42)

        # A validly signed token for activity 42 must not authorize activity 43.
        assert verify_thumbnail_token(43, token) is False

    def test_rejects_forged_token(self):
        from modules.activities.activity_thumbnail.signing import verify_thumbnail_token

        assert verify_thumbnail_token(42, "totally-made-up-token") is False

    def test_rejects_malformed_token_without_raising(self):
        from modules.activities.activity_thumbnail.signing import verify_thumbnail_token

        # Malformed base64/payload (BadData, not just BadSignature) must be
        # swallowed to a False rather than 500 on untrusted query input.
        assert verify_thumbnail_token(1, "a.b.c.d") is False
        assert verify_thumbnail_token(1, "") is False

    def test_token_is_urlsafe_and_nonempty(self):
        from modules.activities.activity_thumbnail.signing import sign_thumbnail_token

        token = sign_thumbnail_token(1)

        assert token
        assert " " not in token

    def test_a_token_older_than_the_max_age_is_rejected(self, monkeypatch):
        """A token minted while an activity was visible must not stay valid
        forever once it is later hidden."""
        import time

        import modules.activities.activity_thumbnail.signing as signing

        monkeypatch.setattr(signing, "_TOKEN_MAX_AGE_SECONDS", 1)
        token = signing.sign_thumbnail_token(42)
        time.sleep(2.1)

        assert signing.verify_thumbnail_token(42, token) is False


class TestThumbnailKeyAndUrl:
    def test_key_format(self):
        from modules.activities.activity_thumbnail.signing import thumbnail_key

        assert thumbnail_key(42) == "42.webp"

    def test_url_none_for_missing_key(self):
        from modules.activities.activity_thumbnail.signing import thumbnail_url

        assert thumbnail_url(None, 1) is None
        assert thumbnail_url("", 1) is None

    @patch("modules.activities.activity_thumbnail.signing.core_signing")
    @patch("modules.activities.activity_thumbnail.signing.core_config")
    def test_url_local_is_signed_route(self, mock_config, mock_signing):
        from modules.activities.activity_thumbnail.signing import thumbnail_url

        mock_config.settings.resolved_storage_uri = "local://data"
        mock_config.ROOT_PATH = "/api/v1"
        mock_signing.sign_token.return_value = "tok123"

        assert thumbnail_url("1.webp", 1) == "/api/v1/activities/1/thumbnail?t=tok123"

    @patch("modules.activities.activity_thumbnail.signing.platform_runtime")
    @patch("modules.activities.activity_thumbnail.signing.core_config")
    def test_url_s3_uses_presigned_storage_url(self, mock_config, mock_runtime):
        from modules.activities.activity_thumbnail.signing import thumbnail_url

        mock_config.settings.resolved_storage_uri = "s3://bucket"
        storage = MagicMock()
        storage.url.return_value = "https://cdn/activity_thumbnails/1.webp"
        mock_runtime.get_active_platform.return_value.storage = storage

        assert thumbnail_url("1.webp", 1) == "https://cdn/activity_thumbnails/1.webp"
        storage.url.assert_called_once_with("activity_thumbnails", "1.webp")

    @patch("modules.activities.activity_thumbnail.signing.core_signing")
    @patch("modules.activities.activity_thumbnail.signing.platform_runtime")
    @patch("modules.activities.activity_thumbnail.signing.core_config")
    def test_url_s3_falls_back_to_signed_route_when_platform_uninitialised(
        self, mock_config, mock_runtime, mock_signing
    ):
        from modules.activities.activity_thumbnail.signing import thumbnail_url

        mock_config.settings.resolved_storage_uri = "s3://bucket"
        mock_config.ROOT_PATH = "/api/v1"
        mock_runtime.get_active_platform.side_effect = RuntimeError("no platform")
        mock_signing.sign_token.return_value = "tok"

        assert thumbnail_url("1.webp", 1) == "/api/v1/activities/1/thumbnail?t=tok"
