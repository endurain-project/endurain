"""Tests for activity media addressing: signed tokens and servable URLs."""

from unittest.mock import MagicMock, patch

_SIGNING = "modules.activities.activity_media.signing"


class TestMediaTokenSigning:
    def test_round_trip_is_valid(self):
        from modules.activities.activity_media.signing import sign_media_token, verify_media_token

        assert verify_media_token(42, sign_media_token(42)) is True

    def test_rejects_token_bound_to_another_media_id(self):
        from modules.activities.activity_media.signing import sign_media_token, verify_media_token

        token = sign_media_token(42)

        assert verify_media_token(43, token) is False

    def test_rejects_forged_token(self):
        from modules.activities.activity_media.signing import verify_media_token

        assert verify_media_token(42, "totally-made-up-token") is False

    def test_rejects_malformed_token_without_raising(self):
        from modules.activities.activity_media.signing import verify_media_token

        assert verify_media_token(1, "a.b.c.d") is False
        assert verify_media_token(1, "") is False

    def test_a_thumbnail_token_does_not_authorize_media(self):
        """The salts must not be interchangeable — both bind a bare integer id."""
        from modules.activities.activity_media.signing import verify_media_token
        from modules.activities.activity_thumbnail.signing import sign_thumbnail_token

        assert verify_media_token(42, sign_thumbnail_token(42)) is False


class TestMediaUrl:
    @patch(f"{_SIGNING}.core_signing")
    @patch(f"{_SIGNING}.core_config")
    def test_url_local_is_signed_route(self, mock_config, mock_signing):
        from modules.activities.activity_media.signing import media_url

        mock_config.settings.resolved_storage_uri = "local://data"
        mock_config.ROOT_PATH = "/api/v1"
        mock_signing.sign_token.return_value = "tok123"

        assert media_url("1_abc.jpg", 1, 5) == "/api/v1/activities/1/media/5/file?t=tok123"

    @patch(f"{_SIGNING}.platform_runtime")
    @patch(f"{_SIGNING}.core_config")
    def test_url_s3_uses_presigned_storage_url(self, mock_config, mock_runtime):
        from modules.activities.activity_media.signing import media_url

        mock_config.settings.resolved_storage_uri = "s3://bucket"
        storage = MagicMock()
        storage.url.return_value = "https://cdn/activity_media/1_abc.jpg"
        mock_runtime.get_active_platform.return_value.storage = storage

        assert media_url("1_abc.jpg", 1, 5) == "https://cdn/activity_media/1_abc.jpg"
        storage.url.assert_called_once_with("activity_media", "1_abc.jpg")

    @patch(f"{_SIGNING}.core_signing")
    @patch(f"{_SIGNING}.platform_runtime")
    @patch(f"{_SIGNING}.core_config")
    def test_url_s3_falls_back_to_signed_route_when_platform_uninitialised(
        self, mock_config, mock_runtime, mock_signing
    ):
        from modules.activities.activity_media.signing import media_url

        mock_config.settings.resolved_storage_uri = "s3://bucket"
        mock_config.ROOT_PATH = "/api/v1"
        mock_runtime.get_active_platform.side_effect = RuntimeError("no platform")
        mock_signing.sign_token.return_value = "tok"

        assert media_url("1_abc.jpg", 1, 5) == "/api/v1/activities/1/media/5/file?t=tok"
