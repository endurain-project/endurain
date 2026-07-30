"""Tests for the activity media service (authorization, storage, cleanup)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import core.exceptions as core_exceptions

_SVC = "modules.activities.activity_media.service"


class TestBuildStorageFilename:
    def test_generates_server_side_name_with_allowed_extension(self):
        from modules.activities.activity_media.service import _build_storage_filename

        name = _build_storage_filename(42, "holiday photo.JPG")

        assert name.startswith("42_")
        assert name.endswith(".jpg")
        # The original stem never survives, so a hostile name cannot be echoed back.
        assert "holiday" not in name

    def test_strips_directory_components(self):
        from modules.activities.activity_media.service import _build_storage_filename

        name = _build_storage_filename(1, "../../etc/passwd.png")

        assert "/" not in name
        assert name.endswith(".png")

    def test_rejects_disallowed_extension(self):
        from modules.activities.activity_media.service import _build_storage_filename

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError) as exc:
            _build_storage_filename(1, "payload.svg")
        assert exc.value.status_code == 415

    def test_rejects_missing_filename(self):
        from modules.activities.activity_media.service import _build_storage_filename

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError) as exc:
            _build_storage_filename(1, None)
        assert exc.value.status_code == 415


class TestListActivityMedia:
    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_crud")
    def test_returns_media_for_owned_activity(self, mock_activity_crud, mock_media_crud):
        from modules.activities.activity_media.service import list_activity_media

        mock_activity_crud.get_activity_by_id_from_user_id.return_value = MagicMock()
        mock_media_crud.get_media_for_activity.return_value = ["media"]

        assert list_activity_media(1, 2, MagicMock()) == ["media"]

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
    @patch(f"{_SVC}.core_file_uploads")
    @patch(f"{_SVC}.core_config")
    @patch(f"{_SVC}.activity_crud")
    def test_saves_file_and_creates_record(self, mock_activity_crud, mock_config, mock_uploads, mock_media_crud):
        from modules.activities.activity_media.service import store_activity_media

        mock_activity_crud.get_activity_by_id_from_user_id.return_value = MagicMock()
        mock_uploads.save_validated_upload_sync.return_value = "/media/1_abc.jpg"
        created = MagicMock(id=9)
        mock_media_crud.create_activity_media.return_value = created

        result = store_activity_media(1, 2, MagicMock(filename="ride.jpg"), MagicMock())

        assert result is created
        mock_media_crud.create_activity_media.assert_called_once()

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.core_file_uploads")
    @patch(f"{_SVC}.activity_crud")
    def test_rejects_activity_owned_by_another_user(self, mock_activity_crud, mock_uploads, mock_media_crud):
        from modules.activities.activity_media.service import store_activity_media

        mock_activity_crud.get_activity_by_id_from_user_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError) as exc:
            store_activity_media(1, 2, MagicMock(filename="ride.jpg"), MagicMock())

        assert exc.value.status_code == 404
        # Nothing is written for an activity the caller does not own.
        mock_uploads.save_validated_upload_sync.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.core_file_uploads")
    @patch(f"{_SVC}.core_config")
    @patch(f"{_SVC}.activity_crud")
    def test_removes_file_when_record_creation_fails(
        self, mock_activity_crud, mock_config, mock_uploads, mock_media_crud
    ):
        from modules.activities.activity_media.service import store_activity_media

        mock_activity_crud.get_activity_by_id_from_user_id.return_value = MagicMock()
        mock_uploads.save_validated_upload_sync.return_value = "/media/1_abc.jpg"
        mock_media_crud.create_activity_media.side_effect = HTTPException(status_code=409, detail="dup")

        with pytest.raises(HTTPException):
            store_activity_media(1, 2, MagicMock(filename="ride.jpg"), MagicMock())

        # A failed upload leaves nothing on disk.
        mock_uploads.safe_remove_within.assert_called_once()


class TestDeleteActivityMedia:
    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.core_file_uploads")
    @patch(f"{_SVC}.core_config")
    @patch(f"{_SVC}.activity_crud")
    def test_deletes_record_and_file(self, mock_activity_crud, mock_config, mock_uploads, mock_media_crud):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="/media/x.jpg")
        mock_activity_crud.get_activity_by_id_from_user_id.return_value = MagicMock()

        delete_activity_media(1, 5, 2, MagicMock())

        mock_media_crud.delete_activity_media.assert_called_once()
        mock_uploads.safe_remove_within.assert_called_once()

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
    @patch(f"{_SVC}.core_file_uploads")
    @patch(f"{_SVC}.core_config")
    @patch(f"{_SVC}.activity_crud")
    def test_cleanup_refusal_is_logged_not_raised(
        self, mock_activity_crud, mock_config, mock_uploads, mock_media_crud, mock_logger
    ):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="/etc/passwd")
        mock_activity_crud.get_activity_by_id_from_user_id.return_value = MagicMock()
        mock_uploads.safe_remove_within.side_effect = HTTPException(status_code=400, detail="outside media dir")

        delete_activity_media(1, 5, 2, MagicMock())

        # The row is still gone; only the file cleanup was refused.
        mock_media_crud.delete_activity_media.assert_called_once()
        mock_logger.warning.assert_called_once()
