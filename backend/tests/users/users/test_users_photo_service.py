"""Tests for users.users.photo_service module."""

import io
import os
import time
import uuid
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import jasil.providers as platform_providers
import pytest
from fastapi import UploadFile
from jasil.backends.storage_local import LocalStorage
from PIL import Image
from starlette.datastructures import Headers
from tests._helpers import images
from tests._helpers.db import create_sqlite_session

import core.blob_sweep as core_blob_sweep
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import modules.users.users.constants as users_constants
import modules.users.users.models as users_models
import modules.users.users.photo_service as users_photo_service

_U1, _U2, _U3, _U7 = (uuid.UUID(int=n) for n in (1, 2, 3, 7))

_CRUD = "modules.users.users.photo_service.users_crud"
_PNG = images.png_with_text()


def _upload(filename: str | None, content_type: str = "image/jpeg") -> UploadFile:
    return UploadFile(io.BytesIO(b"data"), filename=filename, headers=Headers({"content-type": content_type}))


class TestDeletePhotoFiles:
    def test_deletes_every_stored_extension_for_the_user(self):
        storage = MagicMock()
        storage.list_keys.return_value = [f"{_U7}.jpg", f"{_U7}.png"]

        users_photo_service.delete_photo_files(_U7, storage)

        storage.list_keys.assert_called_once_with("user_images", f"{_U7}.")
        assert [call.args for call in storage.delete.call_args_list] == [
            ("user_images", f"{_U7}.jpg"),
            ("user_images", f"{_U7}.png"),
        ]


class TestPhotoOwnership:
    def test_a_stored_key_is_the_user_id_and_the_extension(self):
        assert users_constants.photo_key(_U7, ".png") == f"{_U7}.png"

    def test_a_uuid_stem_names_its_user(self):
        assert users_photo_service._owner_of(f"{_U7}.png") == _U7

    @pytest.mark.parametrize(
        "key", ["7.png", "notes.txt", "__init__.py", f"{_U7.hex}.png", f"{str(uuid.UUID(int=255)).upper()}.png"]
    )
    def test_a_key_that_is_not_a_canonical_uuid_names_no_user(self, key):
        assert users_photo_service._owner_of(key) is None


class TestDeletePhotoFilesFailure:
    def test_a_storage_failure_is_raised_so_the_account_deletion_is_retried(self):
        storage = MagicMock()
        storage.list_keys.side_effect = OSError("storage down")

        with pytest.raises(OSError):
            users_photo_service.delete_photo_files(_U7, storage)


class TestSweepUnreferencedPhotos:
    """The net for a photo a deletion or a replacement left behind."""

    @patch(_CRUD)
    def test_a_key_is_kept_only_while_its_user_names_it(self, mock_crud, mock_db):
        mock_crud.get_photo_keys_by_user_ids.return_value = {
            _U1: f"{_U1}.png",
            _U3: f"/app/backend/data/user_images/{_U3}.png",
        }

        referenced = users_photo_service._referenced_photo_keys(
            [f"{_U1}.png", f"{_U1}.jpg", f"{_U2}.png", f"{_U3}.png", "notes.txt"], mock_db
        )

        # 1.jpg was replaced and 2.png's user is gone; a row not yet rewritten from a legacy path still
        # owns its file, and a key that names no user is not this sweep's to judge.
        assert referenced == {f"{_U1}.png", f"{_U3}.png", "notes.txt"}
        mock_crud.get_photo_keys_by_user_ids.assert_called_once_with([_U1, _U2, _U3], mock_db)

    def test_on_the_plain_local_layout_only_unnamed_photos_go(self, tmp_path):
        """The area is a browsable directory, so it may hold files that are no user's photo."""
        storage = LocalStorage(str(tmp_path), plain_areas=frozenset({"user_images"}))
        for key in (f"{_U1}.png", f"{_U1}.jpg", f"{_U2}.png", f"{_U3}.png", "__init__.py"):
            storage.save("user_images", key, b"x")
        old = time.time() - 2 * core_blob_sweep.MIN_AGE_SECONDS
        for path in (tmp_path / "user_images").iterdir():
            os.utime(path, (old, old))
        db = create_sqlite_session()
        for user_id, photo in ((_U1, f"{_U1}.png"), (_U3, f"/app/backend/data/user_images/{_U3}.png")):
            db.add(
                users_models.Users(
                    id=user_id,
                    name=f"User {user_id.int}",
                    username=f"user{user_id.int}",
                    email=f"user{user_id.int}@example.com",
                    preferred_language="us",
                    access_type="regular",
                    photo_path=photo,
                )
            )
        db.commit()

        with patch("core.blob_sweep.core_database.SessionLocal", return_value=nullcontext(db)):
            assert users_photo_service.sweep_unreferenced_photos(storage) == 2

        assert sorted(storage.list_keys("user_images")) == [f"{_U1}.png", f"{_U3}.png", "__init__.py"]
        db.close()

    @patch("modules.users.users.photo_service.core_blob_sweep.sweep_unreferenced_blobs", return_value=2)
    def test_the_sweep_walks_the_photo_area(self, mock_sweep):
        storage = MagicMock()

        assert users_photo_service.sweep_unreferenced_photos(storage) == 2
        mock_sweep.assert_called_once_with(storage, "user_images", users_photo_service._referenced_photo_keys)


class TestDeletePhoto:
    @patch(_CRUD)
    def test_commits_the_cleared_reference_before_deleting_the_blob(self, mock_crud, mock_db):
        storage = MagicMock()
        mock_crud.replace_photo_key.return_value = f"{_U7}.jpg"
        order = MagicMock()
        order.attach_mock(mock_crud.replace_photo_key, "row")
        order.attach_mock(mock_db.commit, "commit")
        order.attach_mock(storage.delete, "blob")

        users_photo_service.delete_photo(_U7, storage, mock_db)

        assert [call[0] for call in order.mock_calls] == ["row", "commit", "blob"]
        assert mock_crud.replace_photo_key.call_args.args[:2] == (_U7, None)
        storage.delete.assert_called_once_with("user_images", f"{_U7}.jpg")

    @patch(_CRUD)
    def test_a_storage_failure_after_the_commit_does_not_fail_the_request(self, mock_crud, mock_db):
        storage = MagicMock()
        mock_crud.replace_photo_key.return_value = f"{_U7}.jpg"
        storage.delete.side_effect = platform_providers.StorageBackendUnavailableError("storage down")

        users_photo_service.delete_photo(_U7, storage, mock_db)

    @patch(_CRUD)
    def test_a_legacy_path_the_storage_refuses_does_not_fail_the_request(self, mock_crud, mock_db):
        storage = MagicMock()
        mock_crud.replace_photo_key.return_value = f"/app/backend/data/user_images/{_U7}.jpg"
        storage.delete.side_effect = ValueError("escapes base directory")

        users_photo_service.delete_photo(_U7, storage, mock_db)

    @patch(_CRUD)
    def test_an_unexpected_storage_error_propagates(self, mock_crud, mock_db):
        storage = MagicMock()
        mock_crud.replace_photo_key.return_value = f"{_U7}.jpg"
        storage.delete.side_effect = TypeError("bug")

        with pytest.raises(TypeError):
            users_photo_service.delete_photo(_U7, storage, mock_db)


class TestUploadPhoto:
    @patch(_CRUD)
    def test_stores_the_blob_and_records_the_key(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        mock_crud.replace_photo_key.return_value = None
        storage = MagicMock()

        with patch(
            "modules.users.users.photo_service.core_file_uploads.read_validated_upload_sync",
            return_value=_PNG,
        ):
            replaced = users_photo_service.upload_photo(_U7, _upload("Avatar.JPG"), storage, mock_db)

        assert replaced is False
        area, key, data, content_type = storage.save.call_args.args
        assert (area, key, content_type) == ("user_images", f"{_U7}.jpg", "image/jpeg")
        assert not images.has_metadata(data)
        assert mock_crud.replace_photo_key.call_args.args[:2] == (_U7, f"{_U7}.jpg")

    @patch(_CRUD)
    def test_a_photo_that_replaces_one_says_so(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        mock_crud.replace_photo_key.return_value = f"{_U7}.png"

        with patch(
            "modules.users.users.photo_service.core_file_uploads.read_validated_upload_sync",
            return_value=_PNG,
        ):
            replaced = users_photo_service.upload_photo(_U7, _upload("Avatar.JPG"), MagicMock(), mock_db)

        assert replaced is True

    @patch(_CRUD)
    def test_unknown_user_is_not_found(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            users_photo_service.upload_photo(_U7, _upload("a.jpg"), MagicMock(), mock_db)

    @patch(_CRUD)
    def test_missing_filename_is_invalid(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()

        with pytest.raises(core_exceptions.InvalidInputError):
            users_photo_service.upload_photo(_U7, _upload(None), MagicMock(), mock_db)

    @patch(_CRUD)
    def test_unsupported_extension_stores_nothing(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        storage = MagicMock()

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError):
            users_photo_service.upload_photo(_U7, _upload("a.exe"), storage, mock_db)

        storage.save.assert_not_called()
        mock_db.commit.assert_not_called()


class TestStorePhoto:
    @patch(_CRUD)
    def test_the_stored_photo_has_no_metadata_and_is_capped_at_512_pixels(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        storage = MagicMock()
        buffer = io.BytesIO()
        Image.new("RGB", (2000, 1000)).save(buffer, "JPEG", exif=images.exif_with_gps())

        users_photo_service.store_photo(_U7, ".jpg", buffer.getvalue(), storage, mock_db)

        stored = storage.save.call_args.args[2]
        assert not images.has_metadata(stored)
        with Image.open(io.BytesIO(stored)) as image:
            assert image.size == (512, 256)

    @patch(_CRUD)
    def test_the_read_transaction_ends_before_the_blob_is_written(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        storage = MagicMock()
        storage.list_keys.return_value = []
        order = MagicMock()
        order.attach_mock(mock_db.commit, "commit")
        order.attach_mock(storage.save, "save")

        users_photo_service.store_photo(_U7, ".png", _PNG, storage, mock_db)

        assert [call[0] for call in order.mock_calls] == ["commit", "save", "commit"]

    @patch(_CRUD)
    def test_only_the_blob_the_row_named_before_is_removed_after_the_commit(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        mock_crud.replace_photo_key.return_value = f"{_U7}.jpg"
        storage = MagicMock()
        order = MagicMock()
        order.attach_mock(mock_db.commit, "commit")
        order.attach_mock(storage.delete, "delete")

        users_photo_service.store_photo(_U7, ".png", _PNG, storage, mock_db)

        assert [call.args for call in storage.delete.call_args_list] == [("user_images", f"{_U7}.jpg")]
        storage.list_keys.assert_not_called()
        assert [call[0] for call in order.mock_calls][-2:] == ["commit", "delete"]

    @patch(_CRUD)
    def test_the_blob_just_written_is_never_removed(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        mock_crud.replace_photo_key.return_value = f"{_U7}.png"
        storage = MagicMock()

        users_photo_service.store_photo(_U7, ".png", _PNG, storage, mock_db)

        storage.delete.assert_not_called()

    @patch(_CRUD)
    def test_a_failed_cleanup_does_not_fail_the_upload(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        mock_crud.replace_photo_key.return_value = f"{_U7}.jpg"
        storage = MagicMock()
        storage.delete.side_effect = platform_providers.StorageBackendUnavailableError("storage down")

        assert users_photo_service.store_photo(_U7, ".webp", _PNG, storage, mock_db) == f"{_U7}.webp"

    @patch(_CRUD)
    def test_unknown_extension_stores_nothing(self, mock_crud, mock_db):
        storage = MagicMock()

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError):
            users_photo_service.store_photo(_U7, ".gif", _PNG, storage, mock_db)

        storage.save.assert_not_called()

    @patch(_CRUD)
    def test_unknown_user_stores_nothing(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None
        storage = MagicMock()

        with pytest.raises(core_exceptions.NotFoundError):
            users_photo_service.store_photo(_U7, ".png", _PNG, storage, mock_db)

        storage.save.assert_not_called()


class TestUploadPhotoImageFormats:
    @patch(_CRUD)
    def test_a_webp_is_stored_without_its_metadata(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        storage = MagicMock()
        upload = UploadFile(io.BytesIO(images.webp_with_exif()), filename="me.webp")

        users_photo_service.upload_photo(_U7, upload, storage, mock_db)

        _area, _key, data, content_type = storage.save.call_args.args
        assert content_type == "image/webp"
        assert not images.has_metadata(data)

    @pytest.mark.parametrize(
        ("name", "data"),
        [("a.gif", images.gif()), ("a.heic", images.heic_like()), ("a.webp", images.gif())],
        ids=["gif", "heic", "gif-as-webp"],
    )
    @patch(_CRUD)
    def test_gif_and_heic_are_refused(self, mock_crud, mock_db, name: str, data: bytes):
        mock_crud.get_user_by_id.return_value = MagicMock()
        storage = MagicMock()

        with pytest.raises(core_exceptions.DomainError) as exc:
            users_photo_service.upload_photo(_U7, UploadFile(io.BytesIO(data), filename=name), storage, mock_db)

        assert exc.value.status_code in {400, 415}
        storage.save.assert_not_called()

    def test_the_allow_list_is_the_shared_one(self):
        assert set(core_file_uploads.IMAGE_CONTENT_TYPES) == {".jpg", ".jpeg", ".png", ".webp"}
