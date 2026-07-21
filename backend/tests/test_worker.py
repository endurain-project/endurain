"""Tests for the standalone durable-job worker entrypoint."""

import threading
from unittest.mock import patch

import worker


class TestRunWorkerProcess:
    def test_noop_when_jobs_disabled(self):
        with patch("worker.core_config") as cfg, patch("worker.platform_container") as container:
            cfg.settings.JOBS_ENABLED = False
            worker.run_worker_process(stop=threading.Event())
        container.build_platform.assert_not_called()

    def test_builds_platform_and_drains(self):
        stop = threading.Event()
        with (
            patch("worker.core_config") as cfg,
            patch("worker.platform_container") as container,
            patch("worker.platform_runtime") as runtime,
            patch("worker.activity_subscriber_registry") as subscriber_registry,
            patch("worker.jobs_registry") as jobs_registry,
            patch("worker.jobs_service") as service,
            patch("worker.run_worker") as run_worker_mock,
            patch("worker._install_signal_handlers") as install_signals,
        ):
            cfg.settings.JOBS_ENABLED = True
            cfg.settings.JOBS_POLL_INTERVAL_SECONDS = 2.0
            worker.run_worker_process(stop=stop)

        container.build_platform.assert_called_once()
        runtime.set_active_platform.assert_called_once()
        # Every activity durable handler must be registered via the shared surface
        # so the worker can resolve any claimed job — the SAME call main.startup_event
        # makes, so the two entrypoints cannot drift.
        subscriber_registry.register_all_activity_durable_handlers.assert_called_once_with(jobs_registry.registry)
        service.build_runner.assert_called_once()
        install_signals.assert_called_once_with(stop)
        run_worker_mock.assert_called_once()
        assert run_worker_mock.call_args.kwargs["stop"] is stop


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
