"""Tests for core.router — metadata and static-fallback routes."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient

from core.router import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


class TestAbout:
    """Tests for GET {ROOT_PATH}/about — API metadata."""

    def test_returns_correct_metadata(self):
        from core.config import API_VERSION, LICENSE_IDENTIFIER, LICENSE_NAME, LICENSE_URL

        response = client.get("/api/v1/about")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Endurain API"
        assert data["version"] == API_VERSION
        assert data["license"]["name"] == LICENSE_NAME
        assert data["license"]["identifier"] == LICENSE_IDENTIFIER
        assert data["license"]["url"] == LICENSE_URL


class _FileResponseTestMixin:
    """Mixin providing a helper to create a real FileResponse via tmp_path."""

    @staticmethod
    def _make_file_response(tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("content")
        return FileResponse(str(path))


class TestUserImages(_FileResponseTestMixin):
    """Tests for GET /user_images/{user_img}."""

    def test_returns_file_response_when_path_found(self, tmp_path):
        with patch("core.router.core_utils.return_user_img_path") as mock:
            mock.return_value = self._make_file_response(tmp_path)
            response = client.get("/user_images/test.jpg")
            assert response.status_code == 200

    def test_returns_404_when_path_not_found(self):
        with patch("core.router.core_utils.return_user_img_path") as mock:
            mock.return_value = None
            response = client.get("/user_images/test.jpg")
            assert response.status_code == 404
            assert response.json()["detail"] == "User image not found"


class TestServerImages(_FileResponseTestMixin):
    """Tests for GET /server_images/{server_img}."""

    def test_returns_file_response_when_path_found(self, tmp_path):
        with patch("core.router.core_utils.return_server_img_path") as mock:
            mock.return_value = self._make_file_response(tmp_path)
            response = client.get("/server_images/test.jpg")
            assert response.status_code == 200

    def test_returns_404_when_path_not_found(self):
        with patch("core.router.core_utils.return_server_img_path") as mock:
            mock.return_value = None
            response = client.get("/server_images/test.jpg")
            assert response.status_code == 404
            assert response.json()["detail"] == "Server image not found"


class TestActivityMedia(_FileResponseTestMixin):
    """Tests for GET /activity_media/{media}."""

    def test_returns_file_response_when_path_found(self, tmp_path):
        with patch("core.router.core_utils.return_activity_media_path") as mock:
            mock.return_value = self._make_file_response(tmp_path)
            response = client.get("/activity_media/test.jpg")
            assert response.status_code == 200

    def test_returns_404_when_path_not_found(self):
        with patch("core.router.core_utils.return_activity_media_path") as mock:
            mock.return_value = None
            response = client.get("/activity_media/test.jpg")
            assert response.status_code == 404
            assert response.json()["detail"] == "Activity media not found"


class TestActivityThumbnails(_FileResponseTestMixin):
    """Tests for GET /activity_thumbnails/{thumbnail}."""

    def test_returns_file_response_when_path_found(self, tmp_path):
        with patch("core.router.core_utils.return_activity_thumbnail_path") as mock:
            mock.return_value = self._make_file_response(tmp_path)
            response = client.get("/activity_thumbnails/test.jpg")
            assert response.status_code == 200

    def test_returns_404_when_path_not_found(self):
        with patch("core.router.core_utils.return_activity_thumbnail_path") as mock:
            mock.return_value = None
            response = client.get("/activity_thumbnails/test.jpg")
            assert response.status_code == 404
            assert response.json()["detail"] == "Activity thumbnail not found"


class TestCatchAll(_FileResponseTestMixin):
    """Tests for GET /{path:path} — frontend fallback."""

    def test_path_with_extension_returns_file_response(self, tmp_path):
        with patch("core.router.core_utils.return_frontend_index") as mock:
            mock.return_value = self._make_file_response(tmp_path)
            response = client.get("/assets/app.js")
            assert response.status_code == 200

    def test_path_with_extension_returns_404_when_missing(self):
        with patch("core.router.core_utils.return_frontend_index") as mock:
            mock.return_value = None
            response = client.get("/assets/missing.js")
            assert response.status_code == 404
            assert response.json()["detail"] == "Resource not found"

    def test_path_without_extension_returns_index_html(self, tmp_path):
        with patch("core.router.core_utils.return_frontend_index") as mock:
            mock.return_value = self._make_file_response(tmp_path)
            response = client.get("/some/path")
            mock.assert_called_once_with("index.html")
            assert response.status_code == 200

    def test_root_path_returns_index_html(self, tmp_path):
        with patch("core.router.core_utils.return_frontend_index") as mock:
            mock.return_value = self._make_file_response(tmp_path)
            response = client.get("/")
            mock.assert_called_once_with("index.html")
            assert response.status_code == 200

    def test_root_path_returns_404_when_index_html_is_missing(self):
        with patch("core.router.core_utils.return_frontend_index") as mock:
            mock.return_value = None
            response = client.get("/")
            mock.assert_called_once_with("index.html")
            assert response.status_code == 404
            assert response.json()["detail"] == "Frontend index not found"
