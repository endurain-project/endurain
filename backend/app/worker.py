"""Standalone durable-job worker process entrypoint.

Runs outside the API to drain the ``processing_jobs`` queue so job processing
scales independently of request handling. It shares the same database, config,
and platform substrate as the API. The API (or a scheduler process) runs the
outbox relay and lease reaper; this process only claims and runs jobs
(competing consumers coordinated by ``SELECT ... FOR UPDATE SKIP LOCKED``).

Deploy with ``APP_ROLE=worker`` (see ``docker/start.sh``). The API applies
migrations at startup; a worker started earlier waits until the schema is current before it claims a job.
"""

import signal
import threading
from types import FrameType

import jasil.container as platform_container
import jasil.jobs.registry as jobs_registry
import jasil.jobs.service as jobs_service
import jasil.lifecycle as jasil_lifecycle
import jasil.migrations as jasil_migrations
import jasil.runtime as platform_runtime
import jasil.settings as jasil_settings
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

import core.config as core_config
import core.database as core_database
import core.logger as core_logger
import core.platform_settings as core_platform_settings
import model_registry as orm_model_registry
import module_registry as runtime_module_registry

logger = core_logger.get_logger(__name__)

#: Seconds between checks while the API is still migrating the schema.
_SCHEMA_POLL_INTERVAL_SECONDS = 5.0


def _install_signal_handlers(stop: threading.Event) -> None:
    """Set the stop event on SIGTERM/SIGINT for graceful shutdown."""

    def _handle(signum: int, _frame: FrameType | None) -> None:
        logger.info("Worker received a signal; shutting down", extra=core_logger.context(console=True, signal=signum))
        stop.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)


def _alembic_is_at_head() -> bool:
    """Tell whether the database holds the application's latest Alembic revision."""
    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    with core_database.engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision() == head


def _schema_is_current() -> bool:
    """Tell whether the application's and the platform's schemas are both at their latest revision.

    Returns:
        True when neither is behind.

    Raises:
        OperationalError: When the database cannot be reached.
    """
    if not _alembic_is_at_head():
        return False
    try:
        jasil_migrations.verify_schema_current(core_database.engine)
    except RuntimeError:
        return False
    return True


def _wait_for_current_schema(stop: threading.Event) -> None:
    """Block until the schema is current, so no job is claimed against an older one.

    The API applies the migrations, so a worker that starts first polls until it has. It does not migrate.

    Args:
        stop: Set to give up waiting, as on a shutdown signal.

    Raises:
        OperationalError: When the database cannot be reached, which fails startup as it would without this wait.
    """
    if _schema_is_current():
        return
    logger.info(
        "Database schema is not current; waiting for the API to migrate it", extra=core_logger.context(console=True)
    )
    while not stop.wait(_SCHEMA_POLL_INTERVAL_SECONDS):
        if _schema_is_current():
            break
    else:
        return
    logger.info("Database schema is current; starting the worker", extra=core_logger.context(console=True))


def run_worker_process(stop: threading.Event | None = None) -> None:
    """Build the platform, register durable handlers, and drain jobs until stopped.

    Args:
        stop: Optional stop event; defaults to a fresh event wired to SIGTERM/SIGINT.

    Returns:
        None.

    Raises:
        OSError: When ``JOBS_ENABLED`` is false, since a worker has no queue to drain without it.
        OperationalError: When the database cannot be reached while checking its schema.
    """
    logger.info(
        "Durable job worker starting",
        extra=core_logger.context(console=True, version=core_config.API_VERSION),
    )
    if not core_config.settings.JOBS_ENABLED:
        message = "APP_ROLE=worker requires JOBS_ENABLED=true; without durable jobs there is no queue to drain"
        logger.error(message, extra=core_logger.context(console=True))
        raise OSError(message)
    stop = stop or threading.Event()
    _install_signal_handlers(stop)
    _wait_for_current_schema(stop)
    if stop.is_set():
        logger.info("Durable job worker stopped before the schema was current", extra=core_logger.context(console=True))
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
    try:
        jobs_service.run_job_worker(role="worker", stop=stop)
    finally:
        # This process built a platform of its own, so it owns releasing it —
        # under the distributed profile that is a Redis consumer thread and a
        # pool of connections that would otherwise outlive the run.
        # Stop any in-process pool a job handler started here first (each a no-op when it never started), since
        # a pool job still uses the platform.
        runtime_module_registry.shutdown_module_pools()
        jasil_lifecycle.shutdown()
    logger.info("Durable job worker stopped", extra=core_logger.context(console=True))


def main() -> None:
    """Validate the environment, configure logging, and run the worker process."""
    core_config.check_deprecated_env_vars()
    core_config.check_required_env_vars()
    core_config.warn_unsafe_settings()
    core_config.check_required_dirs()
    core_logger.setup_main_logger()
    run_worker_process()


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    main()
