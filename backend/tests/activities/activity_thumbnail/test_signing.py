"""Tests for thumbnail addressing: storage keys, signed tokens, and servable URLs."""

import uuid
from dataclasses import replace
from unittest.mock import patch

ACTIVITY_ID = uuid.UUID("00000000-0000-4000-8000-000000000042")
OTHER_ID = uuid.UUID("00000000-0000-4000-8000-000000000043")


class TestThumbnailTokenSigning:
    def test_round_trip_is_valid(self):
        from modules.activities.activity_thumbnail.signing import (
            sign_thumbnail_token,
            verify_thumbnail_token,
        )

        token = sign_thumbnail_token(ACTIVITY_ID)

        assert verify_thumbnail_token(ACTIVITY_ID, token) is True

    def test_rejects_token_bound_to_another_activity(self):
        from modules.activities.activity_thumbnail.signing import (
            sign_thumbnail_token,
            verify_thumbnail_token,
        )

        token = sign_thumbnail_token(ACTIVITY_ID)

        # A validly signed token for one activity must not authorize another.
        assert verify_thumbnail_token(OTHER_ID, token) is False

    def test_rejects_forged_token(self):
        from modules.activities.activity_thumbnail.signing import verify_thumbnail_token

        assert verify_thumbnail_token(ACTIVITY_ID, "totally-made-up-token") is False

    def test_rejects_malformed_token_without_raising(self):
        from modules.activities.activity_thumbnail.signing import verify_thumbnail_token

        # Malformed base64/payload (BadData, not just BadSignature) must be
        # swallowed to a False rather than 500 on untrusted query input.
        assert verify_thumbnail_token(ACTIVITY_ID, "a.b.c.d") is False
        assert verify_thumbnail_token(ACTIVITY_ID, "") is False

    def test_token_is_urlsafe_and_nonempty(self):
        from modules.activities.activity_thumbnail.signing import sign_thumbnail_token

        token = sign_thumbnail_token(ACTIVITY_ID)

        assert token
        assert " " not in token

    def test_pre_policy_tokens_are_invalidated(self):
        import core.signing as core_signing
        from modules.activities.activity_thumbnail.signing import verify_thumbnail_token

        old_token = core_signing.CapabilitySigner(salt="activity-thumbnail").sign(str(ACTIVITY_ID))

        assert verify_thumbnail_token(ACTIVITY_ID, old_token) is False

    def test_a_token_older_than_the_max_age_is_rejected(self, monkeypatch):
        """A token minted while an activity was visible must not stay valid
        forever once it is later hidden."""
        import time

        import modules.activities.activity_thumbnail.signing as signing

        monkeypatch.setattr(signing, "_SIGNER", replace(signing._SIGNER, max_age_seconds=1, bucket_seconds=1))
        token = signing.sign_thumbnail_token(ACTIVITY_ID)
        time.sleep(2.1)

        assert signing.verify_thumbnail_token(ACTIVITY_ID, token) is False


class TestThumbnailKeyAndUrl:
    """URL shape only — the storage branching itself is covered in tests/core/test_signing.py."""

    def test_key_is_derived_from_the_activity_id(self):
        from modules.activities.activity_thumbnail.signing import thumbnail_key

        assert thumbnail_key(ACTIVITY_ID) == f"{ACTIVITY_ID}.webp"

    def test_no_key_means_no_url(self):
        from modules.activities.activity_thumbnail.signing import thumbnail_url

        assert thumbnail_url(None, ACTIVITY_ID) is None
        assert thumbnail_url("", ACTIVITY_ID) is None

    @patch("modules.activities.activity_thumbnail.signing.core_signing")
    def test_addresses_the_thumbnail_route_with_a_signed_token(self, mock_signing):
        from modules.activities.activity_thumbnail.signing import thumbnail_url

        mock_signing.blob_url.return_value = f"/api/v1/activities/{ACTIVITY_ID}/thumbnail?t=tok"

        assert thumbnail_url(f"{ACTIVITY_ID}.webp", ACTIVITY_ID) == f"/api/v1/activities/{ACTIVITY_ID}/thumbnail?t=tok"
        assert mock_signing.blob_url.call_args.args[:2] == ("activity_thumbnails", f"{ACTIVITY_ID}.webp")
        assert mock_signing.blob_url.call_args.kwargs["local_path"] == f"/activities/{ACTIVITY_ID}/thumbnail"
