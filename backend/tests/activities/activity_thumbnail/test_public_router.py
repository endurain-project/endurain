"""Tests for the public, token-gated activity thumbnail route."""

from unittest.mock import MagicMock, patch

import pytest


class TestReadActivityThumbnailUnit:
    @patch("modules.activities.activity_thumbnail.service.activity_thumbnail_signing")
    def test_serves_webp_bytes_for_valid_token(self, mock_signing):
        from modules.activities.activity_thumbnail.public_router import read_activity_thumbnail

        mock_signing.verify_thumbnail_token.return_value = True
        mock_signing.THUMBNAIL_STORAGE_AREA = "activity_thumbnails"
        mock_signing.thumbnail_key.return_value = "1.webp"
        storage = MagicMock()
        storage.get.return_value = b"webpdata"

        resp = read_activity_thumbnail(1, "tok", storage)

        assert resp.status_code == 200
        assert resp.media_type == "image/webp"
        assert resp.body == b"webpdata"
        assert resp.headers["Cache-Control"] == "private, max-age=3600"
        storage.get.assert_called_once_with("activity_thumbnails", "1.webp")
        mock_signing.verify_thumbnail_token.assert_called_once_with(1, "tok")

    @patch("modules.activities.activity_thumbnail.service.activity_thumbnail_signing")
    def test_404_for_invalid_token_without_touching_storage(self, mock_signing):
        import core.exceptions as core_exceptions
        from modules.activities.activity_thumbnail.public_router import read_activity_thumbnail

        mock_signing.verify_thumbnail_token.return_value = False
        storage = MagicMock()

        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_thumbnail(1, "bad", storage)

        storage.get.assert_not_called()

    @patch("modules.activities.activity_thumbnail.service.activity_thumbnail_signing")
    def test_404_when_blob_missing(self, mock_signing):
        import core.exceptions as core_exceptions
        from modules.activities.activity_thumbnail.public_router import read_activity_thumbnail

        mock_signing.verify_thumbnail_token.return_value = True
        storage = MagicMock()
        storage.get.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_thumbnail(1, "tok", storage)


class TestReadActivityThumbnailEndToEnd:
    def _client(self, storage):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import core.dependencies as core_dependencies
        import core.exceptions as core_exceptions
        import modules.activities.activity_thumbnail.public_router as thumb_router

        app = FastAPI()
        core_exceptions.register_exception_handlers(app)
        app.include_router(thumb_router.router)
        app.dependency_overrides[core_dependencies.get_storage] = lambda: storage
        return TestClient(app)

    def test_valid_signed_token_serves_image(self):
        import modules.activities.activity_thumbnail.signing as signing

        storage = MagicMock()
        storage.get.return_value = b"webpdata"
        client = self._client(storage)

        token = signing.sign_thumbnail_token(7)
        resp = client.get("/7/thumbnail", params={"t": token})

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/webp"
        assert resp.content == b"webpdata"

    def test_forged_token_is_rejected(self):
        storage = MagicMock()
        storage.get.return_value = b"webpdata"
        client = self._client(storage)

        resp = client.get("/7/thumbnail", params={"t": "forged"})

        assert resp.status_code == 404
        storage.get.assert_not_called()

    def test_missing_token_is_unprocessable(self):
        client = self._client(MagicMock())

        resp = client.get("/7/thumbnail")

        assert resp.status_code == 422
