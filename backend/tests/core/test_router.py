"""Tests for core.router: metadata, health and the frontend fallback, on the production application."""

import logging
from datetime import UTC, date, datetime, timedelta

import jasil.audit as jasil_audit
import jasil.runtime as platform_runtime
import jasil.settings as jasil_settings
import pytest
from jasil.providers import StateBackendUnavailableError
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import core.config as core_config
import core.logger as core_logger

_API = core_config.ROOT_PATH


class TestAbout:
    """GET {ROOT_PATH}/about answers the API metadata."""

    def test_returns_correct_metadata(self, client):
        response = client.get(f"{_API}/about")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Endurain API"
        assert data["version"] == core_config.API_VERSION
        assert data["license"]["name"] == core_config.LICENSE_NAME
        assert data["license"]["identifier"] == core_config.LICENSE_IDENTIFIER
        assert data["license"]["url"] == core_config.LICENSE_URL


def _audit_health(**overrides):
    now = datetime.now(UTC)
    health = {
        "write_failures": 0,
        "last_failure_at": None,
        "furthest_partition_date": now.date() + timedelta(days=7),
        "last_checkpoint_at": now - timedelta(minutes=10),
    }
    return {**health, **overrides}


class TestHealth:
    """GET {ROOT_PATH}/health: database-backed liveness, the state backend and the audit trail."""

    @pytest.fixture
    def caplog(self, caplog, app):
        """Capture the application's own logger, which the real app does not propagate to the root logger."""
        app_logger = logging.getLogger(core_logger.ROOT_LOGGER_NAME)
        level = app_logger.level
        app_logger.addHandler(caplog.handler)
        app_logger.setLevel(logging.DEBUG)
        yield caplog
        app_logger.setLevel(level)
        app_logger.removeHandler(caplog.handler)

    @pytest.fixture
    def broken_database(self, monkeypatch):
        """Make the liveness query fail the way an exhausted pool does."""
        execute = Session.execute

        def failing(self, statement, *args, **kwargs):
            if str(statement) == "SELECT 1":
                raise TimeoutError("pool exhausted")
            return execute(self, statement, *args, **kwargs)

        monkeypatch.setattr(Session, "execute", failing)

    @pytest.fixture
    def broken_state(self, monkeypatch, _publish_local_platform):
        """Make the shared state backend unreachable."""

        def down(key):
            raise StateBackendUnavailableError("redis down")

        monkeypatch.setattr(_publish_local_platform.state, "get", down)

    @pytest.fixture
    def audit_health(self, monkeypatch):
        """Return a function that sets what the audit trail reports about itself."""

        def report(**overrides):
            monkeypatch.setattr(jasil_audit, "get_audit_health", lambda: _audit_health(**overrides))

        return report

    def test_returns_ok_when_the_database_the_state_and_the_audit_trail_answer(self, client, audit_health, caplog):
        audit_health()
        with caplog.at_level("WARNING"):
            response = client.get(f"{_API}/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "state": "ok", "audit": "ok"}
        assert caplog.text == ""

    def test_returns_503_when_database_fails(self, client, broken_database):
        response = client.get(f"{_API}/health")

        assert response.status_code == 503
        assert response.headers["Content-Type"].startswith("application/problem+json")
        assert response.headers["Retry-After"] == "5"
        assert response.json()["detail"] == "Database unavailable"

    def test_an_unreachable_state_backend_is_degraded_not_down(self, client, broken_state, audit_health, caplog):
        audit_health()
        with caplog.at_level("DEBUG"):
            response = client.get(f"{_API}/health")

        assert response.status_code == 200
        assert response.json() == {"status": "degraded", "state": "unavailable", "audit": "ok"}
        assert [r.levelname for r in caplog.records if "health probe" in r.getMessage()] == ["DEBUG"]

    def test_the_probe_only_reads(self, client):
        state = platform_runtime.get_active_platform().state

        client.get(f"{_API}/health")

        assert list(state.iter_keys("endurain:health:")) == []

    def test_a_database_failure_wins_over_a_state_failure(self, client, broken_database, broken_state):
        assert client.get(f"{_API}/health").status_code == 503

    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param({"furthest_partition_date": None}, id="no-partition"),
            pytest.param({"furthest_partition_date": datetime.now(UTC).date()}, id="no-partition-for-tomorrow"),
            pytest.param({"furthest_partition_date": date(2000, 1, 1)}, id="old-partition"),
            pytest.param(
                {"last_checkpoint_at": datetime.now(UTC) - timedelta(hours=1, minutes=1)}, id="stale-checkpoint"
            ),
            pytest.param(
                {"last_failure_at": datetime.now(UTC) - timedelta(minutes=5), "write_failures": 1},
                id="recent-write-failure",
            ),
        ],
    )
    def test_an_audit_problem_is_degraded_but_still_200(self, client, audit_health, overrides, caplog):
        audit_health(**overrides)

        with caplog.at_level("DEBUG"):
            response = client.get(f"{_API}/health")

        assert response.status_code == 200
        assert response.json() == {"status": "degraded", "state": "ok", "audit": "degraded"}
        assert [r.levelname for r in caplog.records if "audit trail is degraded" in r.getMessage()] == ["DEBUG"]

    def test_a_partition_for_tomorrow_is_enough(self, client, audit_health):
        audit_health(furthest_partition_date=datetime.now(UTC).date() + timedelta(days=1))

        assert client.get(f"{_API}/health").json()["audit"] == "ok"

    def test_a_failure_older_than_an_hour_is_ok(self, client, audit_health):
        audit_health(last_failure_at=datetime.now(UTC) - timedelta(hours=1, minutes=1), write_failures=3)

        assert client.get(f"{_API}/health").json()["audit"] == "ok"

    def test_a_checkpoint_that_was_never_sealed_is_not_flagged(self, client, audit_health):
        audit_health(last_checkpoint_at=None)

        assert client.get(f"{_API}/health").json()["audit"] == "ok"

    def test_a_disabled_audit_trail_is_ok_and_is_not_read(self, client, audit_health, monkeypatch):
        audit_health(furthest_partition_date=None)
        monkeypatch.setattr(
            jasil_settings,
            "get_settings",
            lambda: jasil_settings.JasilSettings(audit=jasil_settings.AuditSettings(enabled=False)),
        )

        response = client.get(f"{_API}/health")

        assert response.json() == {"status": "ok", "state": "ok", "audit": "ok"}

    @pytest.mark.parametrize("error", [RuntimeError("no sessionmaker"), OperationalError("SELECT 1", {}, Exception())])
    def test_an_unreadable_audit_health_is_degraded_not_a_failure(self, client, monkeypatch, caplog, error):
        def unreadable():
            raise error

        monkeypatch.setattr(jasil_audit, "get_audit_health", unreadable)

        with caplog.at_level("DEBUG"):
            response = client.get(f"{_API}/health")

        assert response.status_code == 200
        assert response.json() == {"status": "degraded", "state": "ok", "audit": "degraded"}
        assert [r.levelname for r in caplog.records if "audit trail is degraded" in r.getMessage()] == ["DEBUG"]


@pytest.fixture
def frontend(tmp_path, monkeypatch):
    """A built frontend bundle with an index page and one asset."""
    bundle = tmp_path / "dist"
    (bundle / "assets").mkdir(parents=True)
    (bundle / "index.html").write_text("<html>the app shell</html>")
    (bundle / "assets" / "app.js").write_text("console.log('app')")
    monkeypatch.setattr(core_config.settings, "FRONTEND_DIR", str(bundle))
    return bundle


@pytest.fixture
def no_frontend(tmp_path, monkeypatch):
    """A frontend directory without a build."""
    monkeypatch.setattr(core_config.settings, "FRONTEND_DIR", str(tmp_path / "missing"))


class TestPrivateBlobsAreNotServedByFilename:
    """Activity media and thumbnails must not be reachable by filename.

    Both used to have an unauthenticated ``GET /<dir>/{name}`` route here, which was a complete bypass of the
    signed-token gates that guard them. The catch-all frontend fallback answers these paths now, so the assertion
    is that no image is returned, not merely that the status is non-200.
    """

    @pytest.mark.parametrize(
        "path",
        [
            "/activity_media/5_abc123.jpg",
            "/activity_thumbnails/5.webp",
            "/user_images/1.png",
        ],
    )
    def test_a_private_file_is_not_served_by_filename(self, client, no_frontend, path):
        assert client.get(path).status_code == 404


class TestCatchAll:
    """GET /{path:path} serves the frontend bundle."""

    def test_path_with_extension_returns_the_file(self, client, frontend):
        response = client.get("/assets/app.js")

        assert response.status_code == 200
        assert response.text == "console.log('app')"

    def test_path_with_extension_returns_404_when_missing(self, client, frontend):
        response = client.get("/assets/missing.js")

        assert response.status_code == 404
        assert response.json()["detail"] == "Resource not found"

    @pytest.mark.parametrize("path", ["/some/path", "/"])
    def test_a_page_without_extension_returns_index_html(self, client, frontend, path):
        response = client.get(path)

        assert response.status_code == 200
        assert response.text == "<html>the app shell</html>"

    def test_a_path_that_climbs_out_of_the_bundle_is_a_404(self, client, frontend):
        (frontend.parent / "secret.txt").write_text("TOPSECRET")

        response = client.get("/assets/..%2f..%2fsecret.txt")

        assert response.status_code == 404
        assert "TOPSECRET" not in response.text

    def test_root_path_returns_404_when_index_html_is_missing(self, client, no_frontend):
        response = client.get("/")

        assert response.status_code == 404
        assert response.json()["detail"] == "Frontend index not found"


class TestFrontendFallbackMethods:
    """Only a GET reaches the frontend fallback; HEAD is served by the GET semantics middleware."""

    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
    def test_another_method_on_a_frontend_path_is_a_404_not_a_405(self, client, frontend, method):
        response = client.request(method, "/some/page")

        assert response.status_code == 404
        assert "the app shell" not in response.text


class TestUnknownApiPath:
    """An unknown path under the API prefix is a 404 problem document, never the SPA shell."""

    def test_an_unknown_api_path_is_a_404_problem_document(self, client, frontend):
        response = client.get(f"{_API}/does/not/exist")

        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["type"] == "urn:endurain:error:not-found"
        assert "the app shell" not in response.text

    def test_the_bare_api_prefix_is_a_404_too(self, client, frontend):
        assert client.get(_API).status_code == 404

    def test_a_frontend_route_that_only_starts_like_the_prefix_still_gets_the_app(self, client, frontend):
        response = client.get(f"{_API}0/x")

        assert response.status_code == 200
        assert "the app shell" in response.text


class TestWellKnownPaths:
    """Nothing under /.well-known/ is the SPA shell: it answers the same 404 problem as an unknown API path."""

    @pytest.mark.parametrize(
        "path",
        [
            "/.well-known/openid-configuration",
            "/.well-known/oauth-authorization-server",
            "/.well-known/jwks.json",
            "/.well-known/nested/anything",
        ],
    )
    def test_a_well_known_path_is_a_404_problem_document(self, client, frontend, path):
        response = client.get(path)

        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["type"] == "urn:endurain:error:not-found"

    def test_a_path_that_only_starts_like_well_known_still_gets_the_app(self, client, frontend):
        response = client.get("/.well-knownx/page")

        assert response.status_code == 200
        assert "the app shell" in response.text
