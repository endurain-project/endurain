"""Tests for the public, token-gated user photo route and its addressing.

Profile photos were the most exposed of the three blob kinds: stored as
``{user_id}.{ext}`` and served from a public path, so the file names enumerated the whole user base
unauthenticated.
"""

import uuid
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions

_U1, _U7, _U42, _U43 = (uuid.UUID(int=n) for n in (1, 7, 42, 43))

_ROUTER = "modules.users.users.photo_router"
_SIGNING = "modules.users.users.signing"
_SERVICE = "modules.users.users.photo_service"


class TestUserImageTokenSigning:
    def test_round_trip_is_valid(self):
        from modules.users.users.signing import sign_user_image_token, verify_user_image_token

        assert verify_user_image_token(_U42, sign_user_image_token(_U42)) is True

    def test_rejects_token_bound_to_another_user(self):
        """The enumeration this route exists to prevent."""
        from modules.users.users.signing import sign_user_image_token, verify_user_image_token

        assert verify_user_image_token(_U43, sign_user_image_token(_U42)) is False

    def test_rejects_forged_and_malformed_tokens(self):
        from modules.users.users.signing import verify_user_image_token

        assert verify_user_image_token(_U42, "made-up") is False
        assert verify_user_image_token(_U42, "") is False

    def test_other_salts_do_not_authorize_a_photo(self):
        """All three blob signers bind the id as a string; the salts must differ."""
        from modules.activities.activity_media.signing import sign_media_token
        from modules.activities.activity_thumbnail.signing import sign_thumbnail_token
        from modules.users.users.signing import verify_user_image_token

        assert verify_user_image_token(_U42, sign_thumbnail_token(_U42)) is False
        assert verify_user_image_token(_U42, sign_media_token(_U42)) is False

    def test_a_token_older_than_the_max_age_is_rejected(self, monkeypatch):
        """A token minted for one photo must not stay valid forever once it is
        replaced or removed."""
        import time

        import modules.users.users.signing as signing

        monkeypatch.setattr(signing, "_SIGNER", replace(signing._SIGNER, max_age_seconds=1, bucket_seconds=1))
        token = signing.sign_user_image_token(_U42)
        time.sleep(2.1)

        assert signing.verify_user_image_token(_U42, token) is False


class TestUserImageUrl:
    """URL shape only — the storage branching itself is covered in tests/core/test_signing.py."""

    def test_no_key_means_no_url(self):
        from modules.users.users.signing import user_image_url

        assert user_image_url(None, _U1) is None
        assert user_image_url(f"{_U1}.png", None) is None

    @patch(f"{_SIGNING}.core_signing")
    def test_addresses_the_photo_route_with_a_signed_token(self, mock_signing):
        from modules.users.users.signing import user_image_url

        mock_signing.blob_url.return_value = f"/api/v1/users/{_U1}/photo?t=tok"

        assert user_image_url(f"{_U1}.png", _U1) == f"/api/v1/users/{_U1}/photo?t=tok"
        assert mock_signing.blob_url.call_args.args[:2] == ("user_images", f"{_U1}.png")
        assert mock_signing.blob_url.call_args.kwargs["local_path"] == f"/users/{_U1}/photo"


class TestReadUserPhoto:
    def test_a_malformed_user_id_is_422(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import core.database as core_database
        from modules.users.users.photo_router import router

        app = FastAPI()
        app.include_router(router, prefix="/users")
        core_exceptions.register_exception_handlers(app)
        app.dependency_overrides[core_database.get_db] = lambda: MagicMock()

        response = TestClient(app).get("/users/7/photo", params={"t": "tok"})

        assert response.status_code == 422

    @patch(f"{_ROUTER}.users_photo_service")
    def test_serves_the_photo_the_service_returns(self, mock_service):
        from modules.users.users.photo_router import read_user_photo

        mock_service.read_photo.return_value = (b"png", "image/png")
        storage = MagicMock()
        db = MagicMock()

        response = read_user_photo(MagicMock(), _U7, storage, db, "tok")

        assert response.status_code == 200
        assert response.media_type == "image/png"
        assert response.body == b"png"
        assert response.headers["Cache-Control"] == "private, max-age=3600"
        mock_service.read_photo.assert_called_once_with(_U7, "tok", storage, db)

    @patch(f"{_ROUTER}.users_photo_service")
    def test_an_unknown_photo_propagates_as_not_found(self, mock_service):
        from modules.users.users.photo_router import read_user_photo

        mock_service.read_photo.side_effect = core_exceptions.NotFoundError("User photo not found")

        with pytest.raises(core_exceptions.NotFoundError):
            read_user_photo(MagicMock(), _U7, MagicMock(), MagicMock(), "forged")


class TestReadPhoto:
    @patch(f"{_SERVICE}.users_crud")
    @patch(f"{_SERVICE}.users_signing")
    def test_serves_the_blob_the_row_names(self, mock_signing, mock_crud, mock_db):
        from modules.users.users.photo_service import read_photo

        mock_signing.verify_user_image_token.return_value = True
        mock_crud.get_photo_key.return_value = f"{_U7}.png"
        storage = MagicMock()
        storage.get.return_value = b"png"

        assert read_photo(_U7, "tok", storage, mock_db) == (b"png", "image/png")
        storage.get.assert_called_once_with("user_images", f"{_U7}.png")

    @patch(f"{_SERVICE}.users_crud")
    @patch(f"{_SERVICE}.users_signing")
    def test_a_blob_left_under_another_extension_is_never_served(self, mock_signing, mock_crud, mock_db):
        from modules.users.users.photo_service import read_photo

        mock_signing.verify_user_image_token.return_value = True
        mock_crud.get_photo_key.return_value = f"{_U7}.png"
        storage = MagicMock()
        storage.get.side_effect = lambda _area, key: b"old" if key == f"{_U7}.jpg" else b"new"

        assert read_photo(_U7, "tok", storage, mock_db)[0] == b"new"

    @patch(f"{_SERVICE}.users_crud")
    @patch(f"{_SERVICE}.users_signing")
    def test_the_read_transaction_ends_before_the_storage_call(self, mock_signing, mock_crud, mock_db):
        from modules.users.users.photo_service import read_photo

        mock_signing.verify_user_image_token.return_value = True
        mock_crud.get_photo_key.return_value = f"{_U7}.png"
        storage = MagicMock()
        order = MagicMock()
        order.attach_mock(mock_db.commit, "commit")
        order.attach_mock(storage.get, "storage")

        read_photo(_U7, "tok", storage, mock_db)

        assert [call[0] for call in order.mock_calls] == ["commit", "storage"]

    @patch(f"{_SERVICE}.users_crud")
    @patch(f"{_SERVICE}.users_signing")
    def test_404_for_an_invalid_token_without_touching_the_database_or_storage(self, mock_signing, mock_crud, mock_db):
        from modules.users.users.photo_service import read_photo

        mock_signing.verify_user_image_token.return_value = False
        storage = MagicMock()

        with pytest.raises(core_exceptions.NotFoundError):
            read_photo(_U7, "forged", storage, mock_db)

        storage.get.assert_not_called()
        mock_crud.get_photo_key.assert_not_called()

    @patch(f"{_SERVICE}.users_crud")
    @patch(f"{_SERVICE}.users_signing")
    def test_404_when_the_user_has_no_photo(self, mock_signing, mock_crud, mock_db):
        from modules.users.users.photo_service import read_photo

        mock_signing.verify_user_image_token.return_value = True
        mock_crud.get_photo_key.return_value = None
        storage = MagicMock()

        with pytest.raises(core_exceptions.NotFoundError):
            read_photo(_U7, "tok", storage, mock_db)

        storage.get.assert_not_called()

    @patch(f"{_SERVICE}.users_crud")
    @patch(f"{_SERVICE}.users_signing")
    def test_404_when_the_blob_is_missing(self, mock_signing, mock_crud, mock_db):
        from modules.users.users.photo_service import read_photo

        mock_signing.verify_user_image_token.return_value = True
        mock_crud.get_photo_key.return_value = f"{_U7}.png"
        storage = MagicMock()
        storage.get.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            read_photo(_U7, "tok", storage, mock_db)


class TestUserReadSerialization:
    def test_photo_path_is_resolved_to_a_url(self):
        """The row stores a key; a client must receive an address."""
        import modules.users.users.serializers as users_serializers

        row = MagicMock()
        row.id = _U7
        row.photo_path = f"{_U7}.png"

        with patch.object(users_serializers.users_schema.UserRead, "model_validate") as validate:
            validate.return_value = MagicMock(photo_path=f"{_U7}.png")
            result = users_serializers.to_read_schema(row)

        assert f"/users/{_U7}/photo?t=" in result.photo_path
