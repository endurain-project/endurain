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
import modules.garmin.provider_registry as garmin_provider_registry
import modules.strava.provider_registry as strava_provider_registry

logger = core_logger.get_logger(__name__)


def _install_signal_handlers(stop: threading.Event) -> None:
    """Set the stop event on SIGTERM/SIGINT for graceful shutdown."""

    def _handle(signum: int, _frame: FrameType | None) -> None:
        logger.info(f"Worker received signal {signum}; shutting down", extra=core_logger.context(console=True))
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
    logger.info(f"Durable job worker starting - {core_config.API_VERSION}", extra=core_logger.context(console=True))
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
    # Importing the worker pulls in JASIL's ProcessingJob model. The app's
    # Base is mapped by the model imports above, so it must happen afterwards.
    from jasil.jobs.worker import run_worker

    substrate_settings = core_platform_settings.build_jasil_settings(core_config.settings)
    jasil_settings.configure(substrate_settings)
    platform = platform_container.build_platform(substrate_settings)
    platform_runtime.set_active_platform(platform)
    # Register every activity durable-job handler so this worker can resolve any
    # claimed job's subscriber_id back to a handler. Uses the SAME shared surface
    # as main.startup_event (app module_registry) so the two entrypoints
    # cannot drift — a handler registered in one but not the other would leave its
    # jobs unresolvable (and dead-lettered) on a dedicated worker.
    runtime_module_registry.configure_activity_contributors()
    runtime_module_registry.register_durable_handlers(jobs_registry.registry)
    # Same reason, for the refresh job: it pulls from whichever providers are
    # registered, and a provider registered in the API but not here would make a
    # refresh claimed by this worker silently return nothing.
    strava_provider_registry.register_activity_provider()
    garmin_provider_registry.register_activity_provider()
    stop = stop or threading.Event()
    _install_signal_handlers(stop)
    runner = jobs_service.build_runner()
    try:
        run_worker(runner, poll_interval_seconds=core_config.settings.JOBS_POLL_INTERVAL_SECONDS, stop=stop)
    finally:
        # This process built a platform of its own, so it owns releasing it —
        # under the distributed profile that is a Redis consumer thread and a
        # pool of connections that would otherwise outlive the run.
        jasil_lifecycle.shutdown()
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
