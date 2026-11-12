"""Tests for the public, token-gated activity media route.

The route replaces two unauthenticated filename-addressed paths (a ``StaticFiles``
mount and ``GET /activity_media/{media}``), so the assertions that matter are: an
invalid token never reaches storage, and a token minted for one activity cannot
be replayed under another activity's URL.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions

ACT = uuid.UUID("00000000-0000-4000-8000-000000000001")
OTHER = uuid.UUID("00000000-0000-4000-8000-000000000099")
MEDIA = uuid.UUID("00000000-0000-4000-8000-0000000000a5")

_ROUTER = "modules.activities.activity_media.public_router"
_SVC = "modules.activities.activity_media.service"


class TestReadActivityMediaFile:
    @patch(f"{_ROUTER}.activity_media_service")
    def test_serves_bytes_for_valid_token(self, mock_service):
        from modules.activities.activity_media.public_router import read_activity_media_file

        mock_service.read_activity_media_blob.return_value = (b"imagedata", "image/jpeg")
        db = MagicMock()
        storage = MagicMock()

        resp = read_activity_media_file(MagicMock(), ACT, MEDIA, "tok", db, storage)

        assert resp.status_code == 200
        assert resp.media_type == "image/jpeg"
        assert resp.body == b"imagedata"
        assert resp.headers["Cache-Control"] == "private, max-age=3600"
        mock_service.read_activity_media_blob.assert_called_once_with(ACT, MEDIA, "tok", storage, db)

    @patch(f"{_ROUTER}.activity_media_service")
    def test_a_refused_read_propagates_as_not_found(self, mock_service):
        from modules.activities.activity_media.public_router import read_activity_media_file

        mock_service.read_activity_media_blob.side_effect = core_exceptions.NotFoundError("Activity media not found")

        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_media_file(MagicMock(), ACT, MEDIA, "forged", MagicMock(), MagicMock())


class TestReadActivityMediaBlob:
    @pytest.fixture(autouse=True)
    def _valid_token(self):
        with patch(f"{_SVC}.activity_media_signing.verify_media_token", return_value=True) as verify:
            self.verify = verify
            yield

    @patch(f"{_SVC}.activity_media_crud")
    def test_returns_bytes_and_content_type(self, mock_crud):
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=ACT, media_path=f"{ACT}_abc.png")
        storage = MagicMock()
        storage.get.return_value = b"png"

        assert read_activity_media_blob(ACT, MEDIA, "tok", storage, MagicMock()) == (b"png", "image/png")
        self.verify.assert_called_once_with(MEDIA, "tok")

    @patch(f"{_SVC}.activity_media_crud")
    def test_jpg_maps_to_the_jpeg_media_type(self, mock_crud):
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=ACT, media_path=f"{ACT}_abc.jpg")
        storage = MagicMock()
        storage.get.return_value = b"jpg"

        assert read_activity_media_blob(ACT, MEDIA, "tok", storage, MagicMock())[1] == "image/jpeg"

    @patch(f"{_SVC}.activity_media_crud")
    def test_an_invalid_token_never_reaches_persistence_or_storage(self, mock_crud):
        from modules.activities.activity_media.service import read_activity_media_blob

        self.verify.return_value = False
        storage = MagicMock()

        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_media_blob(ACT, MEDIA, "forged", storage, MagicMock())

        mock_crud.get_activity_media_by_id.assert_not_called()
        storage.get.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    def test_media_from_another_activity_is_not_served(self, mock_crud):
        """A valid token bound to a media id must not serve it under a foreign activity."""
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=OTHER, media_path=f"{OTHER}_abc.jpg")

        storage = MagicMock()
        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_media_blob(ACT, MEDIA, "tok", storage, MagicMock())
        storage.get.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    def test_missing_record_is_not_found(self, mock_crud):
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = None

        storage = MagicMock()
        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_media_blob(ACT, MEDIA, "tok", storage, MagicMock())
        storage.get.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    def test_missing_blob_is_not_found(self, mock_crud):
        from modules.activities.activity_media.service import read_activity_media_blob

        mock_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=ACT, media_path=f"{ACT}_abc.jpg")
        storage = MagicMock()
        storage.get.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_media_blob(ACT, MEDIA, "tok", storage, MagicMock())


class TestMalformedIds:
    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import core.exceptions as core_exceptions
        import modules.activities.activity_media.public_router as media_router

        app = FastAPI()
        core_exceptions.register_exception_handlers(app)
        app.include_router(media_router.router, prefix="/activities")
        return TestClient(app)

    def test_a_malformed_media_id_is_unprocessable(self):
        resp = self._client().get(f"/activities/{ACT}/media/5/file", params={"t": "tok"})

        assert resp.status_code == 422

    def test_a_malformed_activity_id_is_unprocessable(self):
        resp = self._client().get(f"/activities/1/media/{MEDIA}/file", params={"t": "tok"})

        assert resp.status_code == 422
