"""Tests for the signed thumbnail-URL token helpers."""


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
        assert "/" not in token
