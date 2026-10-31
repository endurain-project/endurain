"""Tests for the public, token-gated activity media route.

The route replaces two unauthenticated filename-addressed paths (a ``StaticFiles``
mount and ``GET /activity_media/{media}``), so the assertions that matter are: an
invalid token never reaches storage, and a token minted for one activity cannot
be replayed under another activity's URL.
"""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions

_ROUTER = "modules.activities.activity_media.public_router"
_SVC = "modules.activities.activity_media.service"


class TestReadActivityMediaFile:
    @patch(f"{_ROUTER}.activity_media_service")
    def test_serves_bytes_for_valid_token(self, mock_service):
        from modules.activities.activity_media.public_router import read_activity_media_file

        mock_service.read_activity_media_blob.return_value = (b"imagedata", "image/jpeg")
        db = MagicMock()
        storage = MagicMock()

        resp = read_activity_media_file(1, 5, "tok", db, storage)

        assert resp.status_code == 200
        assert resp.media_type == "image/jpeg"
        assert resp.body == b"imagedata"
        assert resp.headers["Cache-Control"] == "private, max-age=3600"
        mock_service.read_activity_media_blob.assert_called_once_with(1, 5, "tok", storage, db)

    @patch(f"{_ROUTER}.activity_media_service")
    def test_a_refused_read_propagates_as_not_found(self, mock_service):
        from modules.activities.activity_media.public_router import read_activity_media_file

        mock_service.read_activity_media_blob.side_effect = core_exceptions.NotFoundError("Activity media not found")

        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_media_file(1, 5, "forged", MagicMock(), MagicMock())


class TestReadActivityMediaBlob:
    @pytest.fixture(autouse=True)
    def _valid_token(self):
        with patch(f"{_SVC}.activity_media_signing.verify_media_token", return_value=True) as verify:
            self.verify = verify
            yield

    @patch(f"{_SVC}.activity_media_crud")
    def test_returns_bytes_and_content_type(self, mock_crud):
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="1_abc.png")
        storage = MagicMock()
        storage.get.return_value = b"png"

        assert read_activity_media_blob(1, 5, "tok", storage, MagicMock()) == (b"png", "image/png")
        self.verify.assert_called_once_with(5, "tok")

    @patch(f"{_SVC}.activity_media_crud")
    def test_jpg_maps_to_the_jpeg_media_type(self, mock_crud):
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="1_abc.jpg")
        storage = MagicMock()
        storage.get.return_value = b"jpg"

        assert read_activity_media_blob(1, 5, "tok", storage, MagicMock())[1] == "image/jpeg"

    @patch(f"{_SVC}.activity_media_crud")
    def test_an_invalid_token_never_reaches_persistence_or_storage(self, mock_crud):
        from modules.activities.activity_media.service import read_activity_media_blob

        self.verify.return_value = False
        storage = MagicMock()

        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_media_blob(1, 5, "forged", storage, MagicMock())

        mock_crud.get_activity_media_by_id.assert_not_called()
        storage.get.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    def test_media_from_another_activity_is_not_served(self, mock_crud):
        """A valid token bound to a media id must not serve it under a foreign activity."""
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=99, media_path="99_abc.jpg")

        storage = MagicMock()
        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_media_blob(1, 5, "tok", storage, MagicMock())
        storage.get.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    def test_missing_record_is_not_found(self, mock_crud):
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = None

        storage = MagicMock()
        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_media_blob(1, 5, "tok", storage, MagicMock())
        storage.get.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    def test_missing_blob_is_not_found(self, mock_crud):
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="1_abc.jpg")
        storage = MagicMock()
        storage.get.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_media_blob(1, 5, "tok", storage, MagicMock())
