"""Tests for thumbnail addressing: storage keys, signed tokens, and servable URLs."""

from dataclasses import replace
from unittest.mock import patch


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

    def test_pre_policy_tokens_are_invalidated(self):
        import core.signing as core_signing
        from modules.activities.activity_thumbnail.signing import verify_thumbnail_token

        old_token = core_signing.CapabilitySigner(salt="activity-thumbnail").sign(42)

        assert verify_thumbnail_token(42, old_token) is False

    def test_a_token_older_than_the_max_age_is_rejected(self, monkeypatch):
        """A token minted while an activity was visible must not stay valid
        forever once it is later hidden."""
        import time

        import modules.activities.activity_thumbnail.signing as signing

        monkeypatch.setattr(signing, "_SIGNER", replace(signing._SIGNER, max_age_seconds=1))
        token = signing.sign_thumbnail_token(42)
        time.sleep(2.1)

        assert signing.verify_thumbnail_token(42, token) is False


class TestThumbnailKeyAndUrl:
    """URL shape only — the storage branching itself is covered in tests/core/test_signing.py."""

    def test_key_is_derived_from_the_activity_id(self):
        from modules.activities.activity_thumbnail.signing import thumbnail_key

        assert thumbnail_key(42) == "42.webp"

    def test_no_key_means_no_url(self):
        from modules.activities.activity_thumbnail.signing import thumbnail_url

        assert thumbnail_url(None, 42) is None
        assert thumbnail_url("", 42) is None

    @patch("modules.activities.activity_thumbnail.signing.core_signing")
    def test_addresses_the_thumbnail_route_with_a_signed_token(self, mock_signing):
        from modules.activities.activity_thumbnail.signing import thumbnail_url

        mock_signing.blob_url.return_value = "/api/v1/activities/42/thumbnail?t=tok"

        assert thumbnail_url("42.webp", 42) == "/api/v1/activities/42/thumbnail?t=tok"
        assert mock_signing.blob_url.call_args.args[:2] == ("activity_thumbnails", "42.webp")
        assert mock_signing.blob_url.call_args.kwargs["local_path"] == "/activities/42/thumbnail"
