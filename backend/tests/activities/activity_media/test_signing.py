"""Tests for activity media addressing: signed tokens and servable URLs."""

from dataclasses import replace
from unittest.mock import patch

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

    def test_a_token_older_than_the_max_age_is_rejected(self, monkeypatch):
        """A token minted while the caller could see the media must not stay
        valid forever once that access decision changes."""
        import time

        import modules.activities.activity_media.signing as signing

        monkeypatch.setattr(signing, "_SIGNER", replace(signing._SIGNER, max_age_seconds=1))
        token = signing.sign_media_token(42)
        time.sleep(2.1)

        assert signing.verify_media_token(42, token) is False


class TestMediaUrl:
    """URL shape only — the storage branching itself is covered in tests/core/test_signing.py."""

    @patch(f"{_SIGNING}.core_signing")
    def test_addresses_the_media_route_with_a_signed_token(self, mock_signing):
        from modules.activities.activity_media.signing import media_url

        mock_signing.blob_url.return_value = "/api/v1/activities/1/media/5/file?t=tok"

        assert media_url("1_abc.jpg", 1, 5) == "/api/v1/activities/1/media/5/file?t=tok"
        kwargs = mock_signing.blob_url.call_args.kwargs
        assert mock_signing.blob_url.call_args.args[:2] == ("activity_media", "1_abc.jpg")
        assert kwargs["local_path"] == "/activities/1/media/5/file"
