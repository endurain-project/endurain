"""Wiring for durable job processing — worker lifecycle and scheduled maintenance.

Consumed by ``main`` (start/stop the in-process worker) and the scheduler (relay
the outbox into jobs; reap expired leases). The relay, reaper, and worker all run
on every process and coordinate through ``SELECT ... FOR UPDATE SKIP LOCKED`` plus
the idempotent job fan-out (dedup on ``event_id + subscriber_id``), so replicas
scale horizontally without a single-runner lock — duplicate work is skipped or
deduplicated rather than serialized. All of this is inert unless ``JOBS_ENABLED``
is set.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import core.config as core_config
import core.database as core_database
import core.jobs.crud as jobs_crud
import core.jobs.registry as jobs_registry
import core.jobs.relay as jobs_relay
import core.logger as core_logger
import core.platform.node as platform_node
import core.platform.runtime as platform_runtime
from core.jobs.runner import JobRunner
from core.jobs.worker import BackgroundWorker

# How often the scheduler relays the outbox and reaps expired leases (seconds).
_RELAY_INTERVAL_SECONDS = 5
_REAP_INTERVAL_SECONDS = 60
# Bound how many outbox batches one relay pass drains before yielding.
_MAX_RELAY_BATCHES = 100

_RELAY_JOB_ID = "endurain_outbox_relay"
_REAP_JOB_ID = "endurain_job_reaper"

_worker: BackgroundWorker | None = None


def _worker_id() -> str:
    """Return a per-process worker identifier (host + pid)."""
    return platform_node.process_identity()


def build_runner() -> JobRunner:
    """
    Build a :class:`JobRunner` from settings and the active platform.

    Returns:
        A runner wired to the durable-subscriber registry, the platform clock,
        and the main-database session factory.
    """
    settings = core_config.settings
    platform = platform_runtime.get_active_platform()
    return JobRunner(
        registry=jobs_registry.registry,
        clock=platform.clock,
        session_factory=core_database.SessionLocal,
        worker_id=_worker_id(),
        lease_seconds=settings.JOBS_LEASE_SECONDS,
        batch_size=settings.JOBS_BATCH_SIZE,
        backoff_base_seconds=settings.JOBS_BACKOFF_BASE_SECONDS,
        backoff_max_seconds=settings.JOBS_BACKOFF_MAX_SECONDS,
    )


def start_job_worker() -> None:
    """
    Start the in-process job worker (idempotent).

    Args:
        None.

    Returns:
        None.
    """
    global _worker
    if _worker is not None:
        return
    _worker = BackgroundWorker(build_runner(), poll_interval_seconds=core_config.settings.JOBS_POLL_INTERVAL_SECONDS)
    _worker.start()
    core_logger.print_to_log_and_console("Durable job worker started")


def stop_job_worker() -> None:
    """
    Stop the in-process job worker if it is running.

    Args:
        None.

    Returns:
        None.
    """
    global _worker
    if _worker is None:
        return
    _worker.stop()
    _worker = None
    core_logger.print_to_log_and_console("Durable job worker stopped")


def relay_outbox_scheduled() -> None:
    """
    Relay the outbox into per-subscriber jobs.

    Runs on every replica; ``FOR UPDATE SKIP LOCKED`` gives each relayer a
    disjoint batch and the idempotent fan-out dedups any overlap, so no
    single-runner lock is needed.

    Args:
        None.

    Returns:
        None.
    """
    settings = core_config.settings
    platform = platform_runtime.get_active_platform()
    for _ in range(_MAX_RELAY_BATCHES):
        relayed = jobs_relay.relay_outbox_once(
            registry=jobs_registry.registry,
            clock=platform.clock,
            session_factory=core_database.SessionLocal,
            max_attempts=settings.JOBS_MAX_ATTEMPTS,
            batch_size=settings.JOBS_BATCH_SIZE,
        )
        if relayed == 0:
            break


def reap_expired_jobs_scheduled() -> None:
    """
    Requeue or dead-letter jobs with expired leases.

    Runs on every replica; ``reclaim_expired_leases`` uses ``FOR UPDATE SKIP
    LOCKED`` so concurrent reapers reclaim disjoint rows.

    Args:
        None.

    Returns:
        None.
    """
    platform = platform_runtime.get_active_platform()
    with core_database.SessionLocal() as db:
        reclaimed = jobs_crud.reclaim_expired_leases(now=platform.clock.now(), db=db)
    if reclaimed:
        core_logger.print_to_log(f"Reaped {reclaimed} expired job lease(s)")


def schedule_job_maintenance(scheduler: AsyncIOScheduler) -> None:
    """
    Register the recurring relay and reaper jobs on the scheduler.

    Args:
        scheduler: The application scheduler to register the jobs on.

    Returns:
        None.
    """
    scheduler.add_job(
        relay_outbox_scheduled,
        "interval",
        seconds=_RELAY_INTERVAL_SECONDS,
        id=_RELAY_JOB_ID,
        replace_existing=True,
    )
    scheduler.add_job(
        reap_expired_jobs_scheduled,
        "interval",
        seconds=_REAP_INTERVAL_SECONDS,
        id=_REAP_JOB_ID,
        replace_existing=True,
    )
    core_logger.print_to_log("Scheduled durable-job outbox relay and lease reaper")
