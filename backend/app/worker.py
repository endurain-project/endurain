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

import jasil.container as platform_container
import jasil.jobs.registry as jobs_registry
import jasil.jobs.service as jobs_service
import jasil.lifecycle as jasil_lifecycle
import jasil.runtime as platform_runtime
import jasil.settings as jasil_settings

import core.config as core_config
import core.logger as core_logger
import core.platform_settings as core_platform_settings
import model_registry as orm_model_registry
import module_registry as runtime_module_registry

logger = core_logger.get_logger(__name__)


def _install_signal_handlers(stop: threading.Event) -> None:
    """Set the stop event on SIGTERM/SIGINT for graceful shutdown."""

    def _handle(signum: int, _frame: FrameType | None) -> None:
        logger.info("Worker received a signal; shutting down", extra=core_logger.context(console=True, signal=signum))
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
    logger.info(
        "Durable job worker starting",
        extra=core_logger.context(console=True, version=core_config.API_VERSION),
    )
    if not core_config.settings.JOBS_ENABLED:
        logger.info(
            "JOBS_ENABLED is false; the worker has nothing to do. Exiting.", extra=core_logger.context(console=True)
        )
        return
    # Unlike the API, this process does not import the whole module tree, so
    # the ORM registry would be missing every model a job never touches
    # directly - and a string-target relationship on one that it does touch
    # (Users -> PasswordResetToken) fails to resolve on the first claim.
    orm_model_registry.import_all_models()
    # This process is a dedicated consumer whatever the API's flag says, so the
    # substrate must see the standalone topology it is part of.
    worker_settings = core_config.settings.model_copy(update={"JOBS_RUN_IN_PROCESS_WORKER": False})
    substrate_settings = core_platform_settings.build_jasil_settings(
        worker_settings,
        plain_areas=runtime_module_registry.storage_plain_areas(),
    )
    jasil_settings.configure(substrate_settings)
    platform = platform_container.build_platform(substrate_settings, sources=runtime_module_registry.runtime_sources())
    platform_runtime.set_active_platform(platform)
    # Register every activity durable-job handler so this worker can resolve any
    # claimed job's subscriber_id back to a handler. Uses the SAME shared surface
    # as main.startup_event (app module_registry) so the two entrypoints
    # cannot drift — a handler registered in one but not the other would leave its
    # jobs unresolvable (and dead-lettered) on a dedicated worker.
    runtime_module_registry.configure_application()
    runtime_module_registry.register_durable_handlers(jobs_registry.registry)
    stop = stop or threading.Event()
    _install_signal_handlers(stop)
    try:
        jobs_service.run_job_worker(role="worker", stop=stop)
    finally:
        # This process built a platform of its own, so it owns releasing it —
        # under the distributed profile that is a Redis consumer thread and a
        # pool of connections that would otherwise outlive the run.
        jasil_lifecycle.shutdown()
        # Then any in-process pool a job handler started here (each a no-op when it never started).
        runtime_module_registry.shutdown_module_pools()
    logger.info("Durable job worker stopped", extra=core_logger.context(console=True))


def main() -> None:
    """Validate the environment, configure logging, and run the worker process."""
    core_config.check_deprecated_env_vars()
    core_config.check_required_env_vars()
    core_config.check_required_dirs()
    core_logger.setup_main_logger()
    run_worker_process()


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    main()
