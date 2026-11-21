"""The standalone durable-job worker entrypoint: its refusal to start, its signals and its wait for the schema.

Draining jobs in a worker process needs Redis and a second process, which ``tests/distributed`` runs for real.
"""

import os
import signal
import threading
from pathlib import Path

import jasil.runtime as jasil_runtime
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError

import core.config as core_config
import core.database as core_database
import worker
from tests._helpers import alembic_chain
from tests._helpers import database as test_database

_APP_DIR = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture
def in_app_dir(monkeypatch):
    """Run as the process does, from the application directory where ``alembic.ini`` lives."""
    monkeypatch.chdir(_APP_DIR)


def _set_version(committed_sessions, table: str, revision: str) -> None:
    with committed_sessions() as db:
        db.execute(sa.update(sa.table(table, sa.column("version_num"))).values(version_num=revision))
        db.commit()


@pytest.fixture
def application_schema_behind(committed_sessions):
    _set_version(committed_sessions, "alembic_version", alembic_chain.V0_21_HEAD)


@pytest.fixture
def substrate_schema_behind(committed_sessions):
    _set_version(committed_sessions, "jasil_alembic_version", "rev0001")


class _RepairingStop(threading.Event):
    """A stop event whose wait lets the API finish migrating, as time passing would."""

    def __init__(self, repair) -> None:
        super().__init__()
        self._repair = repair
        self.waits = 0

    def wait(self, timeout: float | None = None) -> bool:
        self.waits += 1
        self._repair()
        return super().wait(0)


class TestRunWorkerProcess:
    def test_refuses_to_start_when_jobs_are_disabled(self, monkeypatch):
        """A worker without the durable queue is a misconfiguration; exiting 0 would hide it behind restarts."""
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", False)
        before = jasil_runtime.get_active_platform()

        with pytest.raises(OSError, match="JOBS_ENABLED"):
            worker.run_worker_process(stop=threading.Event())

        assert jasil_runtime.get_active_platform() is before

    def test_stops_without_building_a_platform_when_told_to_stop_while_the_schema_is_behind(
        self, committed_sessions, in_app_dir, application_schema_behind, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
        before = jasil_runtime.get_active_platform()
        stop = threading.Event()
        stop.set()

        worker.run_worker_process(stop=stop)

        assert jasil_runtime.get_active_platform() is before


class TestInstallSignalHandlers:
    @pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
    def test_a_shutdown_signal_sets_the_stop_event(self, signum):
        previous = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)}
        stop = threading.Event()
        try:
            worker._install_signal_handlers(stop)
            os.kill(os.getpid(), signum)
            assert stop.wait(5)
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)


class TestWaitForCurrentSchema:
    def test_returns_at_once_when_the_schema_is_current(self, committed_sessions, in_app_dir):
        stop = _RepairingStop(lambda: None)

        worker._wait_for_current_schema(stop)

        assert stop.waits == 0

    def test_waits_while_the_schema_is_behind_then_returns(
        self, committed_sessions, in_app_dir, application_schema_behind
    ):
        """A worker started before the API finishes migrating must not claim jobs against the old schema."""
        head = alembic_chain.script_directory().get_current_head()
        stop = _RepairingStop(lambda: _set_version(committed_sessions, "alembic_version", head))

        worker._wait_for_current_schema(stop)

        assert stop.waits == 1
        assert not stop.is_set()

    def test_stops_waiting_when_told_to_stop(self, committed_sessions, in_app_dir, application_schema_behind):
        stop = threading.Event()
        stop.set()

        worker._wait_for_current_schema(stop)

    def test_a_database_that_cannot_be_reached_is_an_error(self, in_app_dir, monkeypatch):
        monkeypatch.setattr(core_database, "engine", test_database.unreachable_engine())

        with pytest.raises(OperationalError):
            worker._wait_for_current_schema(threading.Event())


class TestSchemaIsCurrent:
    def test_true_when_both_schemas_are_current(self, committed_sessions, in_app_dir):
        assert worker._schema_is_current() is True

    def test_false_when_the_application_schema_is_behind(
        self, committed_sessions, in_app_dir, application_schema_behind
    ):
        assert worker._schema_is_current() is False

    def test_false_when_the_substrate_schema_is_behind(self, committed_sessions, in_app_dir, substrate_schema_behind):
        assert worker._schema_is_current() is False
