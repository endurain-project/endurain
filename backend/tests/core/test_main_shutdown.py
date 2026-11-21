"""Tests for what the backend stops, and releases, on shutdown."""

import asyncio
import logging

import jasil.runtime as platform_runtime
import pytest
from sqlalchemy import select

import core.async_bridge as core_async_bridge
import core.database as core_database
import core.logger as core_logger
import core.scheduler as core_scheduler


@pytest.fixture
def main(app):
    """The application module, imported by the harness under the test settings."""
    import main as main_module

    return main_module


@pytest.fixture
def app_log(caplog):
    """Capture the application's logger, which does not propagate to the root logger."""
    logger = logging.getLogger(core_logger.ROOT_LOGGER_NAME)
    level = logger.level
    logger.addHandler(caplog.handler)
    logger.setLevel(logging.DEBUG)
    yield caplog
    logger.setLevel(level)
    logger.removeHandler(caplog.handler)


async def test_shutdown_stops_the_scheduler_and_releases_the_platform_and_the_loop(main, app, committed_sessions):
    core_async_bridge.set_main_loop(asyncio.get_running_loop())
    core_scheduler.scheduler.start(paused=True)

    try:
        main.shutdown_event(app)
        turned = asyncio.Event()
        asyncio.get_running_loop().call_soon(turned.set)
        await turned.wait()

        assert not core_scheduler.scheduler.running
        assert not platform_runtime.is_platform_active()
        assert core_async_bridge._main_loop is None
    finally:
        core_scheduler.stop_scheduler()


def test_shutdown_closes_the_pooled_database_connections(main, app, committed_sessions):
    with committed_sessions() as db:
        db.execute(select(1))
    assert core_database.engine.pool.checkedin() > 0

    main.shutdown_event(app)

    assert core_database.engine.pool.checkedin() == 0


def test_shutdown_without_a_running_scheduler_completes(main, app):
    assert not core_scheduler.scheduler.running

    main.shutdown_event(app)

    assert not platform_runtime.is_platform_active()


def test_a_failure_to_dispose_the_engine_is_logged_and_does_not_stop_the_shutdown(main, app, monkeypatch, app_log):
    def refuse():
        raise RuntimeError("pool is stuck")

    with monkeypatch.context() as patched:
        patched.setattr(core_database.engine, "dispose", refuse)
        main.shutdown_event(app)

    assert "Error disposing database engine on shutdown" in app_log.text
