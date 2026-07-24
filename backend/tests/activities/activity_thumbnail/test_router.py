"""Tests for the public, token-gated activity thumbnail route."""

from unittest.mock import MagicMock, patch

import pytest


class TestReadActivityThumbnailUnit:
    @patch("modules.activities.activity_thumbnail.router.platform_runtime")
    @patch("modules.activities.activity_thumbnail.router.activity_thumbnail_signing")
    def test_serves_webp_bytes_for_valid_token(self, mock_signing, mock_runtime):
        from modules.activities.activity_thumbnail.router import read_activity_thumbnail

        mock_signing.verify_thumbnail_token.return_value = True
        storage = MagicMock()
        storage.get.return_value = b"webpdata"
        mock_runtime.get_active_platform.return_value.storage = storage

        resp = read_activity_thumbnail(1, "tok")

        assert resp.status_code == 200
        assert resp.media_type == "image/webp"
        assert resp.body == b"webpdata"
        assert resp.headers["Cache-Control"] == "private, max-age=3600"
        storage.get.assert_called_once_with("activity_thumbnails", "1.webp")
        mock_signing.verify_thumbnail_token.assert_called_once_with(1, "tok")

    @patch("modules.activities.activity_thumbnail.router.platform_runtime")
    @patch("modules.activities.activity_thumbnail.router.activity_thumbnail_signing")
    def test_404_for_invalid_token_without_touching_storage(self, mock_signing, mock_runtime):
        from fastapi import HTTPException

        from modules.activities.activity_thumbnail.router import read_activity_thumbnail

        mock_signing.verify_thumbnail_token.return_value = False

        with pytest.raises(HTTPException) as exc:
            read_activity_thumbnail(1, "bad")

        assert exc.value.status_code == 404
        mock_runtime.get_active_platform.assert_not_called()

    @patch("modules.activities.activity_thumbnail.router.platform_runtime")
    @patch("modules.activities.activity_thumbnail.router.activity_thumbnail_signing")
    def test_404_when_blob_missing(self, mock_signing, mock_runtime):
        from fastapi import HTTPException

        from modules.activities.activity_thumbnail.router import read_activity_thumbnail

        mock_signing.verify_thumbnail_token.return_value = True
        storage = MagicMock()
        storage.get.return_value = None
        mock_runtime.get_active_platform.return_value.storage = storage

        with pytest.raises(HTTPException) as exc:
            read_activity_thumbnail(1, "tok")

        assert exc.value.status_code == 404


class TestReadActivityThumbnailEndToEnd:
    def _client(self, storage):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import modules.activities.activity_thumbnail.router as thumb_router

        app = FastAPI()
        app.include_router(thumb_router.router)
        patcher = patch("modules.activities.activity_thumbnail.router.platform_runtime")
        mock_runtime = patcher.start()
        mock_runtime.get_active_platform.return_value.storage = storage
        return TestClient(app), patcher

    def test_valid_signed_token_serves_image(self):
        import modules.activities.activity_thumbnail.signing as signing

        storage = MagicMock()
        storage.get.return_value = b"webpdata"
        client, patcher = self._client(storage)
        try:
            token = signing.sign_thumbnail_token(7)
            resp = client.get("/7/thumbnail", params={"t": token})
        finally:
            patcher.stop()

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/webp"
        assert resp.content == b"webpdata"

    def test_forged_token_is_rejected(self):
        storage = MagicMock()
        storage.get.return_value = b"webpdata"
        client, patcher = self._client(storage)
        try:
            resp = client.get("/7/thumbnail", params={"t": "forged"})
        finally:
            patcher.stop()

        assert resp.status_code == 404
        storage.get.assert_not_called()

    def test_missing_token_is_unprocessable(self):
        storage = MagicMock()
        client, patcher = self._client(storage)
        try:
            resp = client.get("/7/thumbnail")
        finally:
            patcher.stop()

        assert resp.status_code == 422
