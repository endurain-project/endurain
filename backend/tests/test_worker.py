"""Tests for the standalone durable-job worker entrypoint."""

import threading
from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy.exc import OperationalError

import worker


class TestRunWorkerProcess:
    def test_refuses_to_start_when_jobs_disabled(self):
        """A worker without the durable queue is a misconfiguration; exiting 0 would hide it behind restarts."""
        with patch("worker.core_config") as cfg, patch("worker.platform_container") as container:
            cfg.settings.JOBS_ENABLED = False
            with pytest.raises(OSError, match="JOBS_ENABLED"):
                worker.run_worker_process(stop=threading.Event())
        container.build_platform.assert_not_called()

    def test_builds_platform_and_drains(self):
        stop = threading.Event()
        with (
            patch("worker.core_config") as cfg,
            patch("worker.core_platform_settings") as platform_settings,
            patch("worker.jasil_settings") as substrate_settings,
            patch("worker.platform_container") as container,
            patch("worker.platform_runtime") as runtime,
            patch("worker.runtime_module_registry") as module_registry,
            patch("worker.jobs_registry") as jobs_registry,
            patch("worker.jobs_service") as service,
            patch("worker.jasil_lifecycle") as lifecycle,
            patch("worker._install_signal_handlers") as install_signals,
            patch("worker._wait_for_current_schema") as wait_for_schema,
        ):
            cfg.settings.JOBS_ENABLED = True
            cfg.settings.JOBS_POLL_INTERVAL_SECONDS = 2.0
            worker.run_worker_process(stop=stop)

        # The worker installs the host's configuration before building, exactly
        # as the API does, or the substrate would read all-defaults settings.
        built = platform_settings.build_jasil_settings.return_value
        substrate_settings.configure.assert_called_once_with(built)
        container.build_platform.assert_called_once_with(built, sources=module_registry.runtime_sources.return_value)
        runtime.set_active_platform.assert_called_once()
        # Every activity durable handler must be registered via the shared surface
        # so the worker can resolve any claimed job — the SAME call main.startup_event
        # makes, so the two entrypoints cannot drift.
        module_registry.configure_application.assert_called_once_with()
        module_registry.register_durable_handlers.assert_called_once_with(jobs_registry.registry)
        assert module_registry.method_calls[2:4] == [
            call.configure_application(),
            call.register_durable_handlers(jobs_registry.registry),
        ]
        install_signals.assert_called_once_with(stop)
        # Jobs are claimed only once the schema is current, so the wait comes before the platform is built.
        wait_for_schema.assert_called_once_with(stop)
        service.run_job_worker.assert_called_once_with(role="worker", stop=stop)
        # Whatever the API's flag says, this process must present the standalone
        # topology, or ``run_job_worker`` refuses to start.
        cfg.settings.model_copy.assert_called_once_with(update={"JOBS_RUN_IN_PROCESS_WORKER": False})
        platform_settings.build_jasil_settings.assert_called_once_with(
            cfg.settings.model_copy.return_value,
            plain_areas=module_registry.storage_plain_areas.return_value,
        )
        # This process built its own platform, so draining is not the end of it:
        # the bus consumer thread and Redis clients have to be released too.
        lifecycle.shutdown.assert_called_once_with()

    def test_stops_module_pools_before_releasing_the_platform(self):
        """A pool job started by a handler still uses the platform, so the pools stop first."""
        manager = MagicMock()
        with (
            patch("worker.core_config") as cfg,
            patch("worker.core_platform_settings"),
            patch("worker.jasil_settings"),
            patch("worker.platform_container"),
            patch("worker.platform_runtime"),
            patch("worker.runtime_module_registry") as module_registry,
            patch("worker.jobs_registry"),
            patch("worker.jobs_service"),
            patch("worker.jasil_lifecycle") as lifecycle,
            patch("worker._install_signal_handlers"),
            patch("worker._wait_for_current_schema"),
        ):
            cfg.settings.JOBS_ENABLED = True
            manager.attach_mock(module_registry.shutdown_module_pools, "pools")
            manager.attach_mock(lifecycle.shutdown, "platform")
            worker.run_worker_process(stop=threading.Event())

        assert [c[0] for c in manager.mock_calls] == ["pools", "platform"]

    def test_releases_the_platform_when_the_run_raises(self):
        with (
            patch("worker.core_config") as cfg,
            patch("worker.core_platform_settings"),
            patch("worker.jasil_settings"),
            patch("worker.platform_container"),
            patch("worker.platform_runtime"),
            patch("worker.runtime_module_registry"),
            patch("worker.jobs_registry"),
            patch("worker.jobs_service") as service,
            patch("worker.jasil_lifecycle") as lifecycle,
            patch("worker._install_signal_handlers"),
            patch("worker._wait_for_current_schema"),
        ):
            service.run_job_worker.side_effect = RuntimeError("boom")
            cfg.settings.JOBS_ENABLED = True
            with pytest.raises(RuntimeError):
                worker.run_worker_process(stop=threading.Event())

        lifecycle.shutdown.assert_called_once_with()


class TestMain:
    def test_runs_preflight_then_process(self):
        with (
            patch("worker.core_config") as cfg,
            patch("worker.core_logger") as logger,
            patch("worker.run_worker_process") as run_process,
        ):
            worker.main()
        cfg.check_deprecated_env_vars.assert_called_once()
        cfg.check_required_env_vars.assert_called_once()
        cfg.check_required_dirs.assert_called_once()
        logger.setup_main_logger.assert_called_once()
        run_process.assert_called_once()


class TestInstallSignalHandlers:
    def test_registers_handlers_that_set_stop(self):
        stop = threading.Event()
        with patch("worker.signal") as mock_signal, patch("worker.core_logger"):
            worker._install_signal_handlers(stop)
            assert mock_signal.signal.call_count == 2
            # The registered handler must set the stop event when a signal arrives.
            handler = mock_signal.signal.call_args_list[0].args[1]
            handler(15, None)
        assert stop.is_set()


class TestWaitForCurrentSchema:
    def test_returns_at_once_when_the_schema_is_current(self):
        stop = MagicMock()
        with patch("worker._schema_is_current", return_value=True) as current:
            worker._wait_for_current_schema(stop)
        current.assert_called_once_with()
        stop.wait.assert_not_called()

    def test_waits_while_the_schema_is_behind_then_returns(self):
        """A worker started before the API finishes migrating must not claim jobs against the old schema."""
        stop = threading.Event()
        with (
            patch("worker._schema_is_current", side_effect=[False, False, True]) as current,
            patch.object(stop, "wait", return_value=False) as wait,
        ):
            worker._wait_for_current_schema(stop)
        assert current.call_count == 3
        assert wait.call_count == 2

    def test_stops_waiting_when_told_to_stop(self):
        stop = threading.Event()
        stop.set()
        with patch("worker._schema_is_current", return_value=False):
            worker._wait_for_current_schema(stop)

    def test_a_database_that_cannot_be_reached_is_an_error(self):
        unreachable = OperationalError("SELECT 1", {}, Exception("down"))
        with patch("worker._schema_is_current", side_effect=unreachable), pytest.raises(OperationalError):
            worker._wait_for_current_schema(threading.Event())


class TestSchemaIsCurrent:
    def test_false_when_the_application_schema_is_behind(self):
        with (
            patch("worker._alembic_is_at_head", return_value=False),
            patch("worker.jasil_migrations") as substrate,
        ):
            assert worker._schema_is_current() is False
        substrate.verify_schema_current.assert_not_called()

    def test_false_when_the_substrate_schema_is_behind(self):
        with (
            patch("worker._alembic_is_at_head", return_value=True),
            patch("worker.jasil_migrations") as substrate,
        ):
            substrate.verify_schema_current.side_effect = RuntimeError("out of date")
            assert worker._schema_is_current() is False

    def test_true_when_both_are_current(self):
        with (
            patch("worker._alembic_is_at_head", return_value=True),
            patch("worker.jasil_migrations"),
        ):
            assert worker._schema_is_current() is True
