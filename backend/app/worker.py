"""Standalone durable-job worker process entrypoint.

Runs outside the API to drain the ``processing_jobs`` queue so job processing
scales independently of request handling. It shares the same database, config,
and platform substrate as the API. The API (or a scheduler process) runs the
outbox relay and lease reaper; this process only claims and runs jobs
(competing consumers coordinated by ``SELECT ... FOR UPDATE SKIP LOCKED``).

Deploy with ``APP_ROLE=worker`` (see ``docker/start.sh``). The API applies
migrations at startup, so start the API (or run migrations) before workers.
"""

import signal
import threading
from types import FrameType

import core.config as core_config
import core.logger as core_logger
import infra.container as platform_container
import infra.jobs.registry as jobs_registry
import infra.jobs.service as jobs_service
import infra.runtime as platform_runtime
import modules.activities.activity.subscribers as activity_subscribers
import modules.activities.activity_geocoding.subscribers as activity_geocoding_subscribers
import modules.activities.activity_streams.subscribers as activity_streams_subscribers
import modules.activities.activity_thumbnail.subscribers as activity_thumbnail_subscribers
from infra.jobs.worker import run_worker


def _install_signal_handlers(stop: threading.Event) -> None:
    """Set the stop event on SIGTERM/SIGINT for graceful shutdown."""

    def _handle(signum: int, _frame: FrameType | None) -> None:
        core_logger.print_to_log_and_console(f"Worker received signal {signum}; shutting down")
        stop.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)


def run_worker_process(stop: threading.Event | None = None) -> None:
    """
    Build the platform, register durable handlers, and drain jobs until stopped.

    Args:
        stop: Optional stop event; defaults to a fresh event wired to SIGTERM/SIGINT.

    Returns:
        None.
    """
    core_logger.print_to_log_and_console(f"Durable job worker starting - {core_config.API_VERSION}")
    if not core_config.settings.JOBS_ENABLED:
        core_logger.print_to_log_and_console("JOBS_ENABLED is false; the worker has nothing to do. Exiting.")
        return
    platform = platform_container.build_platform(core_config.settings)
    platform_runtime.set_active_platform(platform)
    # Register every activity durable-job handler so this worker can resolve any
    # claimed job's subscriber_id back to a handler. Must mirror the durable
    # registrations in main.startup_event — a handler registered there but not
    # here would leave its jobs unresolvable (and dead-lettered) on a dedicated
    # worker.
    activity_thumbnail_subscribers.register_thumbnail_durable_handlers(jobs_registry.registry)
    activity_subscribers.register_activity_notification_durable_handlers(jobs_registry.registry)
    activity_streams_subscribers.register_hr_zone_durable_handlers(jobs_registry.registry)
    activity_geocoding_subscribers.register_geocoding_durable_handlers(jobs_registry.registry)
    stop = stop or threading.Event()
    _install_signal_handlers(stop)
    runner = jobs_service.build_runner()
    run_worker(runner, poll_interval_seconds=core_config.settings.JOBS_POLL_INTERVAL_SECONDS, stop=stop)
    core_logger.print_to_log_and_console("Durable job worker stopped")


def main() -> None:
    """Validate the environment, configure logging, and run the worker process."""
    core_config.check_deprecated_env_vars()
    core_config.check_required_env_vars()
    core_config.check_required_dirs()
    core_logger.setup_main_logger()
    run_worker_process()


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    main()
