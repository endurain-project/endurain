"""Tests for the public, token-gated activity thumbnail route."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

ACTIVITY_ID = uuid.UUID("00000000-0000-4000-8000-000000000042")
OTHER_ID = uuid.UUID("00000000-0000-4000-8000-000000000043")


class TestReadActivityThumbnailUnit:
    @patch("modules.activities.activity_thumbnail.service.activity_thumbnail_signing")
    def test_serves_webp_bytes_for_valid_token(self, mock_signing):
        from modules.activities.activity_thumbnail.public_router import read_activity_thumbnail

        mock_signing.verify_thumbnail_token.return_value = True
        mock_signing.thumbnail_key.return_value = f"{ACTIVITY_ID}.webp"
        storage = MagicMock()
        storage.get.return_value = b"webpdata"

        resp = read_activity_thumbnail(MagicMock(), ACTIVITY_ID, "tok", storage)

        assert resp.status_code == 200
        assert resp.media_type == "image/webp"
        assert resp.body == b"webpdata"
        assert resp.headers["Cache-Control"] == "private, max-age=3600"
        storage.get.assert_called_once_with("activity_thumbnails", f"{ACTIVITY_ID}.webp")
        mock_signing.verify_thumbnail_token.assert_called_once_with(ACTIVITY_ID, "tok")

    @patch("modules.activities.activity_thumbnail.service.activity_thumbnail_signing")
    def test_404_for_invalid_token_without_touching_storage(self, mock_signing):
        import core.exceptions as core_exceptions
        from modules.activities.activity_thumbnail.public_router import read_activity_thumbnail

        mock_signing.verify_thumbnail_token.return_value = False
        storage = MagicMock()

        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_thumbnail(MagicMock(), ACTIVITY_ID, "bad", storage)

        storage.get.assert_not_called()

    @patch("modules.activities.activity_thumbnail.service.activity_thumbnail_signing")
    def test_404_when_blob_missing(self, mock_signing):
        import core.exceptions as core_exceptions
        from modules.activities.activity_thumbnail.public_router import read_activity_thumbnail

        mock_signing.verify_thumbnail_token.return_value = True
        storage = MagicMock()
        storage.get.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            read_activity_thumbnail(MagicMock(), ACTIVITY_ID, "tok", storage)


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

        token = signing.sign_thumbnail_token(ACTIVITY_ID)
        resp = client.get(f"/{ACTIVITY_ID}/thumbnail", params={"t": token})

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/webp"
        assert resp.content == b"webpdata"

    def test_forged_token_is_rejected(self):
        storage = MagicMock()
        storage.get.return_value = b"webpdata"
        client = self._client(storage)

        resp = client.get(f"/{ACTIVITY_ID}/thumbnail", params={"t": "forged"})

        assert resp.status_code == 404
        storage.get.assert_not_called()

    def test_missing_token_is_unprocessable(self):
        client = self._client(MagicMock())

        resp = client.get(f"/{ACTIVITY_ID}/thumbnail")

        assert resp.status_code == 422

    def test_malformed_activity_id_is_unprocessable(self):
        client = self._client(MagicMock())

        resp = client.get("/7/thumbnail", params={"t": "tok"})

        assert resp.status_code == 422
