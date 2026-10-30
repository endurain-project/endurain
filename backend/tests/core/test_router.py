"""Tests for core.router — metadata and static-fallback routes."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient
from jasil.providers import StateBackendUnavailableError

import core.dependencies as core_dependencies
from core.database import get_db
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


class TestHealth:
    """Tests for GET {ROOT_PATH}/health — database-backed liveness and the state backend."""

    @staticmethod
    def _get(db, state):
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[core_dependencies.get_platform_state] = lambda: state
        try:
            return client.get("/api/v1/health")
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(core_dependencies.get_platform_state, None)

    def test_returns_ok_when_the_database_and_the_state_answer(self):
        response = self._get(MagicMock(), MagicMock())

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "state": "ok"}

    def test_returns_503_when_database_fails(self):
        db = MagicMock()
        db.execute.side_effect = TimeoutError("pool exhausted")

        assert self._get(db, MagicMock()).status_code == 503

    def test_an_unreachable_state_backend_is_degraded_not_down(self, caplog):
        state = MagicMock()
        state.get.side_effect = StateBackendUnavailableError("redis down")

        with caplog.at_level("WARNING"):
            response = self._get(MagicMock(), state)

        assert response.status_code == 200
        assert response.json() == {"status": "degraded", "state": "unavailable"}
        assert "health probe" in caplog.text

    def test_the_probe_only_reads(self):
        state = MagicMock()

        self._get(MagicMock(), state)

        state.get.assert_called_once()
        state.set.assert_not_called()

    def test_a_database_failure_wins_over_a_state_failure(self):
        db = MagicMock()
        db.execute.side_effect = TimeoutError("pool exhausted")
        state = MagicMock()
        state.get.side_effect = StateBackendUnavailableError("redis down")

        assert self._get(db, state).status_code == 503


class _FileResponseTestMixin:
    """Mixin providing a helper to create a real FileResponse via tmp_path."""

    @staticmethod
    def _make_file_response(tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("content")
        return FileResponse(str(path))


class TestPrivateBlobsAreNotServedByFilename(_FileResponseTestMixin):
    """Activity media and thumbnails must not be reachable by filename.

    Both used to have an unauthenticated ``GET /<dir>/{name}`` route here, which
    was a complete bypass of the signed-token gates that guard them. The catch-all
    frontend fallback answers these paths now, so the assertion is that no image
    is returned — not merely that the status is non-200.
    """

    def test_activity_media_is_not_served_by_filename(self):
        with patch("core.router.core_utils.return_frontend_index") as mock:
            mock.return_value = None
            response = client.get("/activity_media/5_abc123.jpg")
        assert response.status_code == 404

    def test_activity_thumbnail_is_not_served_by_filename(self):
        with patch("core.router.core_utils.return_frontend_index") as mock:
            mock.return_value = None
            response = client.get("/activity_thumbnails/5.webp")
        assert response.status_code == 404

    def test_user_photo_is_not_served_by_filename(self):
        """Photos are stored as ``{user_id}.{ext}`` — this path enumerated users."""
        with patch("core.router.core_utils.return_frontend_index") as mock:
            mock.return_value = None
            response = client.get("/user_images/1.png")
        assert response.status_code == 404


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


class TestUnknownApiPath(_FileResponseTestMixin):
    """An unknown path under the API prefix is a 404 problem document, never the SPA shell."""

    @staticmethod
    def _client() -> TestClient:
        import core.exceptions as core_exceptions

        problem_app = FastAPI()
        core_exceptions.register_exception_handlers(problem_app)
        problem_app.include_router(router)
        return TestClient(problem_app)

    def test_an_unknown_api_path_is_a_404_problem_document(self, tmp_path):
        with patch("core.router.core_utils.return_frontend_index") as mock:
            mock.return_value = self._make_file_response(tmp_path)
            response = self._client().get("/api/v1/does/not/exist")

        mock.assert_not_called()
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["type"] == "urn:endurain:error:not-found"

    def test_the_bare_api_prefix_is_a_404_too(self, tmp_path):
        with patch("core.router.core_utils.return_frontend_index") as mock:
            mock.return_value = self._make_file_response(tmp_path)
            response = self._client().get("/api/v1")

        assert response.status_code == 404

    def test_a_frontend_route_that_only_starts_like_the_prefix_still_gets_the_app(self, tmp_path):
        with patch("core.router.core_utils.return_frontend_index") as mock:
            mock.return_value = self._make_file_response(tmp_path)
            response = self._client().get("/api/v10/x")

        assert response.status_code == 200
