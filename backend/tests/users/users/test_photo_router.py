"""Tests for the public, token-gated user photo route and its addressing.

Profile photos were the most exposed of the three blob kinds: stored as
``{user_id}.{ext}`` and served from a public path, so walking ``1.png``,
``2.png``, … enumerated the whole user base unauthenticated.
"""

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

_ROUTER = "modules.users.users.photo_router"
_SIGNING = "modules.users.users.signing"


class TestUserImageTokenSigning:
    def test_round_trip_is_valid(self):
        from modules.users.users.signing import sign_user_image_token, verify_user_image_token

        assert verify_user_image_token(42, sign_user_image_token(42)) is True

    def test_rejects_token_bound_to_another_user(self):
        """The enumeration this route exists to prevent."""
        from modules.users.users.signing import sign_user_image_token, verify_user_image_token

        assert verify_user_image_token(43, sign_user_image_token(42)) is False

    def test_rejects_forged_and_malformed_tokens(self):
        from modules.users.users.signing import verify_user_image_token

        assert verify_user_image_token(42, "made-up") is False
        assert verify_user_image_token(42, "") is False

    def test_other_salts_do_not_authorize_a_photo(self):
        """All three blob signers bind a bare integer id; the salts must differ."""
        from modules.activities.activity_media.signing import sign_media_token
        from modules.activities.activity_thumbnail.signing import sign_thumbnail_token
        from modules.users.users.signing import verify_user_image_token

        assert verify_user_image_token(42, sign_thumbnail_token(42)) is False
        assert verify_user_image_token(42, sign_media_token(42)) is False

    def test_a_token_older_than_the_max_age_is_rejected(self, monkeypatch):
        """A token minted for one photo must not stay valid forever once it is
        replaced or removed."""
        import time

        import modules.users.users.signing as signing

        monkeypatch.setattr(signing, "_SIGNER", replace(signing._SIGNER, max_age_seconds=1))
        token = signing.sign_user_image_token(42)
        time.sleep(2.1)

        assert signing.verify_user_image_token(42, token) is False


class TestUserImageUrl:
    """URL shape only — the storage branching itself is covered in tests/core/test_signing.py."""

    def test_no_key_means_no_url(self):
        from modules.users.users.signing import user_image_url

        assert user_image_url(None, 1) is None
        assert user_image_url("1.png", None) is None

    @patch(f"{_SIGNING}.core_signing")
    def test_addresses_the_photo_route_with_a_signed_token(self, mock_signing):
        from modules.users.users.signing import user_image_url

        mock_signing.blob_url.return_value = "/api/v1/users/1/photo?t=tok"

        assert user_image_url("1.png", 1) == "/api/v1/users/1/photo?t=tok"
        assert mock_signing.blob_url.call_args.args[:2] == ("user_images", "1.png")
        assert mock_signing.blob_url.call_args.kwargs["local_path"] == "/users/1/photo"


class TestReadUserPhoto:
    @patch(f"{_ROUTER}.platform_runtime")
    @patch(f"{_ROUTER}.users_signing")
    def test_serves_the_first_matching_extension(self, mock_signing, mock_runtime):
        from modules.users.users.photo_router import read_user_photo

        mock_signing.verify_user_image_token.return_value = True
        mock_signing.USER_IMAGE_STORAGE_AREA = "user_images"
        storage = mock_runtime.get_active_platform.return_value.storage
        storage.get.side_effect = lambda _area, key: b"png" if key == "7.png" else None

        response = read_user_photo(7, "tok")

        assert response.status_code == 200
        assert response.media_type == "image/png"
        assert response.body == b"png"
        assert response.headers["Cache-Control"] == "private, max-age=3600"

    @patch(f"{_ROUTER}.platform_runtime")
    @patch(f"{_ROUTER}.users_signing")
    def test_404_for_an_invalid_token_without_touching_storage(self, mock_signing, mock_runtime):
        from modules.users.users.photo_router import read_user_photo

        mock_signing.verify_user_image_token.return_value = False

        with pytest.raises(HTTPException) as exc:
            read_user_photo(7, "forged")

        assert exc.value.status_code == 404
        mock_runtime.get_active_platform.assert_not_called()

    @patch(f"{_ROUTER}.platform_runtime")
    @patch(f"{_ROUTER}.users_signing")
    def test_404_when_no_photo_is_stored(self, mock_signing, mock_runtime):
        from modules.users.users.photo_router import read_user_photo

        mock_signing.verify_user_image_token.return_value = True
        mock_runtime.get_active_platform.return_value.storage.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            read_user_photo(7, "tok")

        assert exc.value.status_code == 404


class TestUserReadSerialization:
    def test_photo_path_is_resolved_to_a_url(self):
        """The row stores a key; a client must receive an address."""
        import modules.users.users.crud as users_crud

        row = MagicMock()
        row.id = 7
        row.photo_path = "7.png"

        with patch.object(users_crud.users_schema.UsersRead, "model_validate") as validate:
            validate.return_value = MagicMock(photo_path="7.png")
            result = users_crud._to_read_schema(row)

        assert "/users/7/photo?t=" in result.photo_path
