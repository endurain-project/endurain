"""Tests for core.router — metadata and static-fallback routes."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient
from jasil.providers import StateBackendUnavailableError
from sqlalchemy.exc import OperationalError

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
    def _audit_health(**overrides):
        now = datetime.now(UTC)
        health = {
            "write_failures": 0,
            "last_failure_at": None,
            "furthest_partition_date": now.date() + timedelta(days=7),
            "last_checkpoint_at": now - timedelta(minutes=10),
        }
        return {**health, **overrides}

    @pytest.fixture(autouse=True)
    def _healthy_audit(self):
        settings = MagicMock()
        settings.audit.enabled = True
        with (
            patch("jasil.settings.get_settings", return_value=settings),
            patch("jasil.audit.get_audit_health", return_value=self._audit_health()) as healthy,
        ):
            self.healthy = healthy
            self.settings = settings
            yield

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
        assert response.json() == {"status": "ok", "state": "ok", "audit": "ok"}

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
        assert response.json() == {"status": "degraded", "state": "unavailable", "audit": "ok"}
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

    def test_a_healthy_probe_does_not_log(self, caplog):
        with caplog.at_level("WARNING"):
            self._get(MagicMock(), MagicMock())

        assert caplog.text == ""

    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param({"furthest_partition_date": None}, id="no-partition"),
            pytest.param(
                {"furthest_partition_date": datetime.now(UTC).date()},
                id="no-partition-for-tomorrow",
            ),
            pytest.param({"furthest_partition_date": date(2000, 1, 1)}, id="old-partition"),
            pytest.param(
                {"last_checkpoint_at": datetime.now(UTC) - timedelta(hours=1, minutes=1)},
                id="stale-checkpoint",
            ),
            pytest.param(
                {"last_failure_at": datetime.now(UTC) - timedelta(minutes=5), "write_failures": 1},
                id="recent-write-failure",
            ),
        ],
    )
    def test_an_audit_problem_is_degraded_but_still_200(self, overrides, caplog):
        self.healthy.return_value = self._audit_health(**overrides)

        with caplog.at_level("WARNING"):
            response = self._get(MagicMock(), MagicMock())

        assert response.status_code == 200
        assert response.json() == {"status": "degraded", "state": "ok", "audit": "degraded"}
        assert "audit" in caplog.text.lower()

    def test_a_partition_for_tomorrow_is_enough(self):
        self.healthy.return_value = self._audit_health(
            furthest_partition_date=datetime.now(UTC).date() + timedelta(days=1)
        )

        assert self._get(MagicMock(), MagicMock()).json()["audit"] == "ok"

    def test_a_failure_older_than_an_hour_is_ok(self):
        self.healthy.return_value = self._audit_health(
            last_failure_at=datetime.now(UTC) - timedelta(hours=1, minutes=1), write_failures=3
        )

        assert self._get(MagicMock(), MagicMock()).json()["audit"] == "ok"

    def test_a_checkpoint_that_was_never_sealed_is_not_flagged(self):
        self.healthy.return_value = self._audit_health(last_checkpoint_at=None)

        assert self._get(MagicMock(), MagicMock()).json()["audit"] == "ok"

    def test_a_disabled_audit_trail_is_ok_and_is_not_read(self):
        self.healthy.return_value = self._audit_health(furthest_partition_date=None)
        self.settings.audit.enabled = False

        response = self._get(MagicMock(), MagicMock())

        assert response.json() == {"status": "ok", "state": "ok", "audit": "ok"}
        self.healthy.assert_not_called()

    @pytest.mark.parametrize("error", [RuntimeError("no sessionmaker"), OperationalError("SELECT 1", {}, Exception())])
    def test_an_unreadable_audit_health_is_degraded_not_a_failure(self, caplog, error):
        self.healthy.side_effect = error

        with caplog.at_level("WARNING"):
            response = self._get(MagicMock(), MagicMock())

        assert response.status_code == 200
        assert response.json() == {"status": "degraded", "state": "ok", "audit": "degraded"}
        assert "audit" in caplog.text.lower()

    def test_a_database_failure_does_not_read_the_audit_health(self):
        db = MagicMock()
        db.execute.side_effect = TimeoutError("pool exhausted")

        assert self._get(db, MagicMock()).status_code == 503
        self.healthy.assert_not_called()


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
