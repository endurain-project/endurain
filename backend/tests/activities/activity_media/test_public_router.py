"""Tests for the public, token-gated activity media route.

The route replaces two unauthenticated filename-addressed paths (a ``StaticFiles``
mount and ``GET /activity_media/{media}``), so the assertions that matter are: an
invalid token never reaches storage, and a token minted for one activity cannot
be replayed under another activity's URL.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

_ROUTER = "modules.activities.activity_media.public_router"


class TestReadActivityMediaFile:
    @patch(f"{_ROUTER}.activity_media_service")
    @patch(f"{_ROUTER}.activity_media_signing")
    def test_serves_bytes_for_valid_token(self, mock_signing, mock_service):
        from modules.activities.activity_media.public_router import read_activity_media_file

        mock_signing.verify_media_token.return_value = True
        mock_service.read_activity_media_blob.return_value = (b"imagedata", "image/jpeg")

        resp = read_activity_media_file(1, 5, "tok", MagicMock())

        assert resp.status_code == 200
        assert resp.media_type == "image/jpeg"
        assert resp.body == b"imagedata"
        assert resp.headers["Cache-Control"] == "private, max-age=3600"
        mock_signing.verify_media_token.assert_called_once_with(5, "tok")

    @patch(f"{_ROUTER}.activity_media_service")
    @patch(f"{_ROUTER}.activity_media_signing")
    def test_404_for_invalid_token_without_reading_the_blob(self, mock_signing, mock_service):
        from modules.activities.activity_media.public_router import read_activity_media_file

        mock_signing.verify_media_token.return_value = False

        with pytest.raises(HTTPException) as exc:
            read_activity_media_file(1, 5, "forged", MagicMock())

        assert exc.value.status_code == 404
        mock_service.read_activity_media_blob.assert_not_called()

    @patch(f"{_ROUTER}.activity_media_service")
    @patch(f"{_ROUTER}.activity_media_signing")
    def test_404_when_blob_missing(self, mock_signing, mock_service):
        from modules.activities.activity_media.public_router import read_activity_media_file

        mock_signing.verify_media_token.return_value = True
        mock_service.read_activity_media_blob.return_value = None

        with pytest.raises(HTTPException) as exc:
            read_activity_media_file(1, 5, "tok", MagicMock())

        assert exc.value.status_code == 404


class TestReadActivityMediaBlob:
    _SVC = "modules.activities.activity_media.service"

    @patch(f"{_SVC}._storage")
    @patch(f"{_SVC}.activity_media_crud")
    def test_returns_bytes_and_content_type(self, mock_crud, mock_storage):
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="1_abc.png")
        mock_storage.return_value.get.return_value = b"png"

        assert read_activity_media_blob(1, 5, MagicMock()) == (b"png", "image/png")

    @patch(f"{_SVC}._storage")
    @patch(f"{_SVC}.activity_media_crud")
    def test_jpg_maps_to_the_jpeg_media_type(self, mock_crud, mock_storage):
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="1_abc.jpg")
        mock_storage.return_value.get.return_value = b"jpg"

        assert read_activity_media_blob(1, 5, MagicMock())[1] == "image/jpeg"

    @patch(f"{_SVC}._storage")
    @patch(f"{_SVC}.activity_media_crud")
    def test_media_from_another_activity_is_not_served(self, mock_crud, mock_storage):
        """A valid token bound to a media id must not serve it under a foreign activity."""
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=99, media_path="99_abc.jpg")

        assert read_activity_media_blob(1, 5, MagicMock()) is None
        mock_storage.return_value.get.assert_not_called()

    @patch(f"{_SVC}._storage")
    @patch(f"{_SVC}.activity_media_crud")
    def test_missing_record_returns_none(self, mock_crud, mock_storage):
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = None

        assert read_activity_media_blob(1, 5, MagicMock()) is None
        mock_storage.return_value.get.assert_not_called()

    @patch(f"{_SVC}._storage")
    @patch(f"{_SVC}.activity_media_crud")
    def test_missing_blob_returns_none(self, mock_crud, mock_storage):
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="1_abc.jpg")
        mock_storage.return_value.get.return_value = None

        assert read_activity_media_blob(1, 5, MagicMock()) is None
