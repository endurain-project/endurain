"""Tests for what the backend does when the process starts: the real lifespan on the migrated test database."""

import threading
from collections.abc import Iterator
from pathlib import Path

import jasil.runtime as platform_runtime
import jasil.testing as jasil_testing
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

import core.async_bridge as core_async_bridge
import core.config as core_config
import core.database as core_database
import core.scheduler as core_scheduler
import module_registry as runtime_module_registry
import modules.server_settings.constants as server_settings_constants
import modules.users.contributor_registry as users_contributor_registry
from tests._factories.server_settings import edit_server_settings

#: Alembic reads ``alembic.ini`` from the working directory, which is the application directory in a deployment.
APP_DIR = Path(__file__).parents[2] / "app"
WORKER_THREAD = "durable-job-worker"


@pytest.fixture
def main(app):
    """The application module, imported by the harness under the test settings."""
    import main as main_module

    return main_module


@pytest.fixture
def fresh_process(app, monkeypatch) -> Iterator[None]:
    """A process whose startup has not run: nothing registered or published, in the application directory.

    Startup registers the audit catalog and the contributors itself, so the registrations the harness made for the
    test are cleared first. Afterwards the scheduler is stopped and emptied and the job worker is gone, so a later
    test in this worker process finds neither.
    """
    monkeypatch.chdir(APP_DIR)
    jasil_testing.reset_all()
    users_contributor_registry.clear()
    core_scheduler.stop_scheduler()
    core_scheduler.scheduler.remove_all_jobs()
    yield
    core_scheduler.stop_scheduler()
    core_scheduler.scheduler.remove_all_jobs()
    assert WORKER_THREAD not in _thread_names()


def _thread_names() -> list[str]:
    return [thread.name for thread in threading.enumerate() if thread.is_alive()]


def _job_id(description: str) -> str:
    return "endurain_" + "_".join(description.lower().split())


def _scheduled_ids() -> set[str]:
    return {job.id for job in core_scheduler.scheduler.get_jobs()}


def _declared_job_ids() -> set[str]:
    jobs = (*core_scheduler.platform_jobs(), *runtime_module_registry.recurring_jobs())
    return {_job_id(job.description) for job in jobs}


def test_the_lifespan_starts_and_serves_with_the_scheduler_and_releases_everything_on_exit(
    main, app, fresh_process, committed_sessions
):
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json()["state"] == "ok"
        assert core_scheduler.scheduler.running
        assert platform_runtime.is_platform_active()
        assert app.state.platform is platform_runtime.get_active_platform()
        assert core_async_bridge._main_loop is not None
        assert _declared_job_ids() <= _scheduled_ids()

    assert not core_scheduler.scheduler.running
    assert not platform_runtime.is_platform_active()
    assert core_async_bridge._main_loop is None
    with core_database.SessionLocal() as db:
        assert db.scalar(select(1)) == 1


def test_the_lifespan_releases_everything_when_the_server_stops_on_an_error(
    main, app, fresh_process, committed_sessions
):
    with pytest.raises(RuntimeError, match="stopped by the operator"), TestClient(app):
        assert core_scheduler.scheduler.running
        raise RuntimeError("stopped by the operator")

    assert not core_scheduler.scheduler.running
    assert not platform_runtime.is_platform_active()


def test_the_job_worker_and_job_maintenance_run_when_durable_jobs_are_on(
    main, app, fresh_process, committed_sessions, monkeypatch
):
    monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
    monkeypatch.setattr(core_config.settings, "JOBS_RUN_IN_PROCESS_WORKER", True)

    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert WORKER_THREAD in _thread_names()
        assert {"jasil_outbox_relay", "jasil_job_reaper", "jasil_dead_letter_delivery"} <= _scheduled_ids()

    assert WORKER_THREAD not in _thread_names()


def test_durable_jobs_off_runs_no_worker_and_no_job_maintenance(main, app, fresh_process, committed_sessions):
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert WORKER_THREAD not in _thread_names()
        assert not {"jasil_outbox_relay", "jasil_job_reaper", "jasil_dead_letter_delivery"} & _scheduled_ids()


def test_a_failing_startup_task_is_logged_with_its_name_and_startup_still_serves(
    main, app, fresh_process, committed_sessions, app_log
):
    with committed_sessions() as db:
        db.execute(text("DROP TABLE password_reset_tokens CASCADE"))
        db.commit()

    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert core_scheduler.scheduler.running

    failures = [record for record in app_log.records if record.getMessage() == "Startup task failed"]
    assert [record.levelname for record in failures] == ["ERROR"]
    assert failures[0].task == "purge_expired_password_reset_tokens"
    assert failures[0].exc_info is not None


def test_startup_allows_the_configured_tile_server_in_the_content_security_policy(
    main, app, fresh_process, committed_sessions
):
    with committed_sessions() as db:
        edit_server_settings(db, tileserver_url="https://tiles.example.org/{z}/{x}/{y}.png")
        db.commit()

    with TestClient(app):
        assert app.state.allowed_tile_domains == [
            *server_settings_constants.DEFAULT_ALLOWED_TILE_DOMAINS,
            "https://tiles.example.org",
        ]


class TestSafeRun:
    def test_a_task_that_raises_is_logged_with_its_label_and_returns_nothing(self, main, app_log):
        def refuse() -> None:
            raise RuntimeError("provider is down")

        assert main._safe_run("sync_provider", refuse) is None

        (record,) = [record for record in app_log.records if record.getMessage() == "Startup task failed"]
        assert (record.levelname, record.task) == ("ERROR", "sync_provider")
        assert isinstance(record.exc_info[1], RuntimeError)

    def test_a_task_that_succeeds_returns_its_result_with_its_arguments(self, main):
        assert main._safe_run("add", lambda left, right=0: left + right, 2, right=3) == 5

    async def test_an_async_task_that_raises_is_logged_with_its_label_and_returns_nothing(self, main, app_log):
        async def refuse() -> None:
            raise RuntimeError("dns is down")

        assert await main._safe_run_async("resolve", refuse) is None

        (record,) = [record for record in app_log.records if record.getMessage() == "Startup task failed"]
        assert (record.levelname, record.task) == ("ERROR", "resolve")

    async def test_an_async_task_that_succeeds_returns_its_result(self, main):
        async def double(value: int) -> int:
            return value * 2

        assert await main._safe_run_async("double", double, 4) == 8


def test_the_tile_domains_fall_back_to_the_defaults_when_the_database_read_fails(
    main, app, committed_sessions, app_log
):
    app.state.allowed_tile_domains = ["https://stale.example.org"]
    with committed_sessions() as db:
        db.execute(text("DROP TABLE server_settings CASCADE"))
        db.commit()

    main._init_allowed_tile_domains(app)

    assert app.state.allowed_tile_domains == server_settings_constants.DEFAULT_ALLOWED_TILE_DOMAINS
    assert app.state.allowed_tile_domains is not server_settings_constants.DEFAULT_ALLOWED_TILE_DOMAINS
    assert "Error initializing tile domains, using defaults" in app_log.text
