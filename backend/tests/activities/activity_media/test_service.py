"""Tests for the activity media service (authorization, storage, cleanup)."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions

_SVC = "modules.activities.activity_media.service"


class TestBuildStorageKey:
    def test_generates_server_side_key_with_allowed_extension(self):
        from modules.activities.activity_media.service import _build_storage_key

        key = _build_storage_key(42, "holiday photo.JPG")

        assert key.startswith("42_")
        assert key.endswith(".jpg")
        # The original stem never survives, so a hostile name cannot be echoed back.
        assert "holiday" not in key

    def test_strips_directory_components(self):
        from modules.activities.activity_media.service import _build_storage_key

        key = _build_storage_key(1, "../../etc/passwd.png")

        assert "/" not in key
        assert key.endswith(".png")

    def test_rejects_disallowed_extension(self):
        from modules.activities.activity_media.service import _build_storage_key

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError) as exc:
            _build_storage_key(1, "payload.svg")
        assert exc.value.status_code == 415

    def test_rejects_missing_filename(self):
        from modules.activities.activity_media.service import _build_storage_key

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError) as exc:
            _build_storage_key(1, None)
        assert exc.value.status_code == 415


class TestListActivityMedia:
    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_crud")
    def test_returns_media_for_owned_activity(self, mock_activity_crud, mock_media_crud):
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import list_activity_media

        mock_activity_crud.get_activity_by_id_from_user_id.return_value = MagicMock()
        mock_media_crud.get_media_for_activity.return_value = [
            ActivityMediaRecord(id=3, activity_id=1, media_path="1_abc.jpg", media_type=1)
        ]

        media = list_activity_media(1, 2, MagicMock())

        # The storage key never reaches the caller; a servable URL does.
        assert len(media) == 1
        assert not hasattr(media[0], "media_path")
        assert "/activities/1/media/3/file?t=" in media[0].url

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_crud")
    def test_returns_empty_when_activity_not_owned(self, mock_activity_crud, mock_media_crud):
        from modules.activities.activity_media.service import list_activity_media

        mock_activity_crud.get_activity_by_id_from_user_id.return_value = None

        assert list_activity_media(1, 2, MagicMock()) == []
        mock_media_crud.get_media_for_activity.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_crud")
    def test_returns_empty_when_no_media(self, mock_activity_crud, mock_media_crud):
        from modules.activities.activity_media.service import list_activity_media

        mock_activity_crud.get_activity_by_id_from_user_id.return_value = MagicMock()
        mock_media_crud.get_media_for_activity.return_value = []

        assert list_activity_media(1, 2, MagicMock()) == []


class TestStoreActivityMedia:
    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}._storage")
    @patch(f"{_SVC}.core_file_uploads")
    @patch(f"{_SVC}.activity_crud")
    def test_saves_blob_and_creates_record(self, mock_activity_crud, mock_uploads, mock_storage, mock_media_crud):
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media

        mock_activity_crud.get_activity_by_id_from_user_id.return_value = MagicMock()
        mock_uploads.read_validated_upload_sync.return_value = b"bytes"
        storage = mock_storage.return_value
        mock_media_crud.create_activity_media.return_value = ActivityMediaRecord(
            id=9, activity_id=1, media_path="1_abc.jpg", media_type=1
        )

        result = store_activity_media(1, 2, MagicMock(filename="ride.jpg", content_type="image/jpeg"), MagicMock())

        assert result.id == 9
        assert "/activities/1/media/9/file?t=" in result.url
        area, key, data, content_type = storage.save.call_args.args
        assert area == "activity_media"
        assert key.startswith("1_") and key.endswith(".jpg")
        assert data == b"bytes"
        assert content_type == "image/jpeg"
        # The row records the storage key, never a filesystem path.
        assert mock_media_crud.create_activity_media.call_args.args[1] == key

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}._storage")
    @patch(f"{_SVC}.core_file_uploads")
    @patch(f"{_SVC}.activity_crud")
    def test_rejects_activity_owned_by_another_user(
        self, mock_activity_crud, mock_uploads, mock_storage, mock_media_crud
    ):
        from modules.activities.activity_media.service import store_activity_media

        mock_activity_crud.get_activity_by_id_from_user_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError) as exc:
            store_activity_media(1, 2, MagicMock(filename="ride.jpg"), MagicMock())

        assert exc.value.status_code == 404
        # Nothing is read or stored for an activity the caller does not own.
        mock_uploads.read_validated_upload_sync.assert_not_called()
        mock_storage.return_value.save.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}._storage")
    @patch(f"{_SVC}.core_file_uploads")
    @patch(f"{_SVC}.activity_crud")
    def test_removes_blob_when_record_creation_fails(
        self, mock_activity_crud, mock_uploads, mock_storage, mock_media_crud
    ):
        from modules.activities.activity_media.service import store_activity_media

        mock_activity_crud.get_activity_by_id_from_user_id.return_value = MagicMock()
        mock_uploads.read_validated_upload_sync.return_value = b"bytes"
        storage = mock_storage.return_value
        mock_media_crud.create_activity_media.side_effect = core_exceptions.ConflictError("dup")

        with pytest.raises(core_exceptions.ConflictError):
            store_activity_media(1, 2, MagicMock(filename="ride.jpg", content_type="image/jpeg"), MagicMock())

        # A failed upload leaves no orphaned blob.
        stored_key = storage.save.call_args.args[1]
        storage.delete.assert_called_once_with("activity_media", stored_key)


class TestDeleteActivityMedia:
    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}._storage")
    @patch(f"{_SVC}.activity_crud")
    def test_deletes_record_and_blob(self, mock_activity_crud, mock_storage, mock_media_crud):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="1_abc.jpg")
        mock_activity_crud.get_activity_by_id_from_user_id.return_value = MagicMock()

        delete_activity_media(1, 5, 2, MagicMock())

        mock_media_crud.delete_activity_media.assert_called_once()
        mock_storage.return_value.delete.assert_called_once_with("activity_media", "1_abc.jpg")

    @patch(f"{_SVC}.activity_media_crud")
    def test_missing_media_is_404(self, mock_media_crud):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError) as exc:
            delete_activity_media(1, 5, 2, MagicMock())
        assert exc.value.status_code == 404

    @patch(f"{_SVC}.activity_media_crud")
    def test_media_belonging_to_another_activity_is_404(self, mock_media_crud):
        """The media id must match the activity in the route path.

        Now that the route is ``/activities/{activity_id}/media/{media_id}``, a
        media id reached through an unrelated activity's URL must not resolve —
        otherwise the path would claim a relationship the handler never checked.
        """
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=99, media_path="/media/x.jpg")

        with pytest.raises(core_exceptions.NotFoundError) as exc:
            delete_activity_media(1, 5, 2, MagicMock())

        assert exc.value.status_code == 404
        mock_media_crud.delete_activity_media.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_crud")
    def test_media_on_another_users_activity_is_404(self, mock_activity_crud, mock_media_crud):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="/media/x.jpg")
        mock_activity_crud.get_activity_by_id_from_user_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError) as exc:
            delete_activity_media(1, 5, 2, MagicMock())

        assert exc.value.status_code == 404
        # 404 rather than 403 so media ids cannot be probed, and nothing is deleted.
        mock_media_crud.delete_activity_media.assert_not_called()

    @patch(f"{_SVC}.logger")
    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}._storage")
    @patch(f"{_SVC}.activity_crud")
    def test_cleanup_failure_is_logged_not_raised(self, mock_activity_crud, mock_storage, mock_media_crud, mock_logger):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="1_abc.jpg")
        mock_activity_crud.get_activity_by_id_from_user_id.return_value = MagicMock()
        mock_storage.return_value.delete.side_effect = OSError("backend down")

        delete_activity_media(1, 5, 2, MagicMock())

        # The row is still gone; only the blob cleanup failed.
        mock_media_crud.delete_activity_media.assert_called_once()
        mock_logger.warning.assert_called_once()
