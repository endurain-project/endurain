"""Tests for users.users.photo_service module."""

import io
import os
import time
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest
from fastapi import UploadFile
from jasil.backends.storage_local import LocalStorage
from starlette.datastructures import Headers
from tests._helpers.db import create_sqlite_session

import core.blob_sweep as core_blob_sweep
import core.exceptions as core_exceptions
import modules.users.users.models as users_models
import modules.users.users.photo_service as users_photo_service

_CRUD = "modules.users.users.photo_service.users_crud"


def _upload(filename: str | None, content_type: str = "image/jpeg") -> UploadFile:
    return UploadFile(io.BytesIO(b"data"), filename=filename, headers=Headers({"content-type": content_type}))


class TestDeletePhotoFiles:
    def test_deletes_every_stored_extension_for_the_user(self):
        storage = MagicMock()
        storage.list_keys.return_value = ["7.jpg", "7.png"]

        users_photo_service.delete_photo_files(7, storage)

        storage.list_keys.assert_called_once_with("user_images", "7.")
        assert [call.args for call in storage.delete.call_args_list] == [
            ("user_images", "7.jpg"),
            ("user_images", "7.png"),
        ]


class TestDeletePhotoFilesFailure:
    def test_a_storage_failure_is_raised_so_the_account_deletion_is_retried(self):
        storage = MagicMock()
        storage.list_keys.side_effect = OSError("storage down")

        with pytest.raises(OSError):
            users_photo_service.delete_photo_files(7, storage)


class TestSweepUnreferencedPhotos:
    """The net for a photo a deletion or a replacement left behind."""

    @patch(_CRUD)
    def test_a_key_is_kept_only_while_its_user_names_it(self, mock_crud, mock_db):
        mock_crud.get_photo_keys_by_user_ids.return_value = {1: "1.png", 3: "/app/backend/data/user_images/3.png"}

        referenced = users_photo_service._referenced_photo_keys(
            ["1.png", "1.jpg", "2.png", "3.png", "notes.txt"], mock_db
        )

        # 1.jpg was replaced and 2.png's user is gone; a row not yet rewritten from a legacy path still
        # owns its file, and a key that names no user is not this sweep's to judge.
        assert referenced == {"1.png", "3.png", "notes.txt"}
        mock_crud.get_photo_keys_by_user_ids.assert_called_once_with([1, 2, 3], mock_db)

    def test_on_the_plain_local_layout_only_unnamed_photos_go(self, tmp_path):
        """The area is a browsable directory, so it may hold files that are no user's photo."""
        storage = LocalStorage(str(tmp_path), plain_areas=frozenset({"user_images"}))
        for key in ("1.png", "1.jpg", "2.png", "3.png", "__init__.py"):
            storage.save("user_images", key, b"x")
        old = time.time() - 2 * core_blob_sweep.MIN_AGE_SECONDS
        for path in (tmp_path / "user_images").iterdir():
            os.utime(path, (old, old))
        db = create_sqlite_session()
        for user_id, photo in ((1, "1.png"), (3, "/app/backend/data/user_images/3.png")):
            db.add(
                users_models.Users(
                    id=user_id,
                    name=f"User {user_id}",
                    username=f"user{user_id}",
                    email=f"user{user_id}@example.com",
                    preferred_language="us",
                    access_type="regular",
                    photo_path=photo,
                )
            )
        db.commit()

        with patch("core.blob_sweep.core_database.SessionLocal", return_value=nullcontext(db)):
            assert users_photo_service.sweep_unreferenced_photos(storage) == 2

        assert sorted(storage.list_keys("user_images")) == ["1.png", "3.png", "__init__.py"]
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
        mock_crud.replace_photo_key.return_value = "7.jpg"
        order = MagicMock()
        order.attach_mock(mock_crud.replace_photo_key, "row")
        order.attach_mock(mock_db.commit, "commit")
        order.attach_mock(storage.delete, "blob")

        users_photo_service.delete_photo(7, storage, mock_db)

        assert [call[0] for call in order.mock_calls] == ["row", "commit", "blob"]
        assert mock_crud.replace_photo_key.call_args.args[:2] == (7, None)
        storage.delete.assert_called_once_with("user_images", "7.jpg")

    @patch(_CRUD)
    def test_a_storage_failure_after_the_commit_does_not_fail_the_request(self, mock_crud, mock_db):
        storage = MagicMock()
        mock_crud.replace_photo_key.return_value = "7.jpg"
        storage.delete.side_effect = OSError("storage down")

        users_photo_service.delete_photo(7, storage, mock_db)


class TestUploadPhoto:
    @patch(_CRUD)
    def test_stores_the_blob_and_records_the_key(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        storage = MagicMock()

        with patch(
            "modules.users.users.photo_service.core_file_uploads.read_validated_upload_sync",
            return_value=b"bytes",
        ):
            key = users_photo_service.upload_photo(7, _upload("Avatar.JPG"), storage, mock_db)

        assert key == "7.jpg"
        assert storage.save.call_args.args == ("user_images", "7.jpg", b"bytes", "image/jpeg")
        assert mock_crud.replace_photo_key.call_args.args[:2] == (7, "7.jpg")

    @patch(_CRUD)
    def test_unknown_user_is_not_found(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            users_photo_service.upload_photo(7, _upload("a.jpg"), MagicMock(), mock_db)

    @patch(_CRUD)
    def test_missing_filename_is_invalid(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()

        with pytest.raises(core_exceptions.InvalidInputError):
            users_photo_service.upload_photo(7, _upload(None), MagicMock(), mock_db)

    @patch(_CRUD)
    def test_unsupported_extension_stores_nothing(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        storage = MagicMock()

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError):
            users_photo_service.upload_photo(7, _upload("a.exe"), storage, mock_db)

        storage.save.assert_not_called()
        mock_db.commit.assert_not_called()


class TestStorePhoto:
    @patch(_CRUD)
    def test_the_read_transaction_ends_before_the_blob_is_written(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        storage = MagicMock()
        storage.list_keys.return_value = []
        order = MagicMock()
        order.attach_mock(mock_db.commit, "commit")
        order.attach_mock(storage.save, "save")

        users_photo_service.store_photo(7, ".png", b"bytes", storage, mock_db)

        assert [call[0] for call in order.mock_calls] == ["commit", "save", "commit"]

    @patch(_CRUD)
    def test_only_the_blob_the_row_named_before_is_removed_after_the_commit(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        mock_crud.replace_photo_key.return_value = "7.jpg"
        storage = MagicMock()
        order = MagicMock()
        order.attach_mock(mock_db.commit, "commit")
        order.attach_mock(storage.delete, "delete")

        users_photo_service.store_photo(7, ".png", b"bytes", storage, mock_db)

        assert [call.args for call in storage.delete.call_args_list] == [("user_images", "7.jpg")]
        storage.list_keys.assert_not_called()
        assert [call[0] for call in order.mock_calls][-2:] == ["commit", "delete"]

    @patch(_CRUD)
    def test_the_blob_just_written_is_never_removed(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        mock_crud.replace_photo_key.return_value = "7.png"
        storage = MagicMock()

        users_photo_service.store_photo(7, ".png", b"bytes", storage, mock_db)

        storage.delete.assert_not_called()

    @patch(_CRUD)
    def test_a_failed_cleanup_does_not_fail_the_upload(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = MagicMock()
        mock_crud.replace_photo_key.return_value = "7.jpg"
        storage = MagicMock()
        storage.delete.side_effect = OSError("storage down")

        assert users_photo_service.store_photo(7, ".webp", b"bytes", storage, mock_db) == "7.webp"

    @patch(_CRUD)
    def test_unknown_extension_stores_nothing(self, mock_crud, mock_db):
        storage = MagicMock()

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError):
            users_photo_service.store_photo(7, ".gif", b"bytes", storage, mock_db)

        storage.save.assert_not_called()

    @patch(_CRUD)
    def test_unknown_user_stores_nothing(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None
        storage = MagicMock()

        with pytest.raises(core_exceptions.NotFoundError):
            users_photo_service.store_photo(7, ".png", b"bytes", storage, mock_db)

        storage.save.assert_not_called()
