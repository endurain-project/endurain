"""Background scheduler: the APScheduler instance and the jobs it is handed.

Knows *how* to schedule, never *what*. It used to import ``modules.activities``,
``modules.auth``, ``modules.strava`` and ``modules.garmin`` to enumerate their
recurring work, which put the platform above the domain — the wrong way round,
and the reason adding a scheduled job to a module meant editing ``core``.

Each module now declares its own work in a ``scheduled_jobs`` module and the
composition root (``main``) hands the collected list to :func:`start_scheduler`.
The only jobs declared here are core's and the substrate's own.
"""

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import jasil.retention as platform_retention
import jasil.runtime as platform_runtime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import core.logger as core_logger
import core.network as core_network

logger = core_logger.get_logger(__name__)

scheduler = AsyncIOScheduler()


@dataclass(frozen=True)
class ScheduledJob:
    """
    One recurring job a module asks the scheduler to run.

    Attributes:
        func: Callable to execute.
        minutes: Interval between runs, in minutes.
        description: Human-readable description, also the job's stable ID.
        args: Positional arguments passed to func.
        lock_name: Distributed lock guarding execution, or ``None`` when every
            scheduler process may run the job.
    """

    func: Callable[..., object]
    minutes: int
    description: str
    args: Sequence[object] = field(default_factory=tuple)
    lock_name: str | None = None


def _run_locked_job(lock_name: str, func: Callable[..., object], *args: object) -> object | None:
    """Run a synchronous scheduled job only while holding its distributed lock.

    Args:
        lock_name: Stable coordination-lock name.
        func: Scheduled operation to run.
        *args: Positional arguments forwarded to the operation.

    Returns:
        The operation result, or ``None`` when another replica holds the lock.
    """
    with platform_runtime.get_active_platform().lock.try_acquire(lock_name) as acquired:
        if not acquired:
            logger.debug(
                "Scheduler job skipped because another replica holds its lock",
                extra=core_logger.context(lock_name=lock_name),
            )
            return None
        return func(*args)


async def _run_locked_async_job(lock_name: str, func: Callable[..., object], *args: object) -> object | None:
    """Run an asynchronous scheduled job only while holding its distributed lock.

    Args:
        lock_name: Stable coordination-lock name.
        func: Scheduled coroutine function to run.
        *args: Positional arguments forwarded to the operation.

    Returns:
        The awaited result, or ``None`` when another replica holds the lock.
    """
    with platform_runtime.get_active_platform().lock.try_acquire(lock_name) as acquired:
        if not acquired:
            logger.debug(
                "Scheduler job skipped because another replica holds its lock",
                extra=core_logger.context(lock_name=lock_name),
            )
            return None
        result = func(*args)
        if inspect.isawaitable(result):
            return await result
        return result


def platform_jobs() -> tuple[ScheduledJob, ...]:
    """
    Return the recurring jobs owned by core and the platform substrate.

    Args:
        None.

    Returns:
        The platform's own scheduled jobs.

    Raises:
        None.
    """
    return (
        ScheduledJob(
            core_network.refresh_trusted_proxy_hostnames,
            1,
            "refresh trusted proxy hostname resolutions",
        ),
        # Prunes the substrate's append-only bookkeeping tables (event_log,
        # relayed outbox rows, completed jobs) so they don't grow without bound.
        # Self-gated by the retention settings and single-runner via the lock.
        ScheduledJob(
            platform_retention.prune_expired_records,
            1440,
            "prune expired platform bookkeeping records",
        ),
    )


def start_scheduler(jobs: Sequence[ScheduledJob] = ()) -> None:
    """
    Start the scheduler and register the given recurring jobs.

    Args:
        jobs: The recurring jobs to register, collected by the caller from each
            module's ``scheduled_jobs`` declaration.

    Returns:
        None.

    Raises:
        None.
    """
    if not scheduler.running:
        scheduler.start()

    for job in jobs:
        func = job.func
        args: Sequence[object] = job.args
        if job.lock_name is not None:
            func = _run_locked_async_job if inspect.iscoroutinefunction(job.func) else _run_locked_job
            args = (job.lock_name, job.func, *job.args)
        add_scheduler_job(func, "interval", job.minutes, args, job.description)

    # Clears any backlog promptly, so a frequently-restarted deployment does not
    # starve the daily prune declared in platform_jobs().
    run_once(
        platform_retention.prune_expired_records,
        job_id="endurain_prune_expired_records_oneshot",
        description="retention prune",
    )


def run_once(func: Callable[..., object], *, job_id: str, description: str) -> None:
    """
    Queue a one-shot job on the scheduler's own executor.

    Args:
        func: Callable to execute once.
        job_id: Fixed APScheduler job ID, so repeated calls coalesce into a
            single pending run.
        description: Human-readable description, used in log messages.

    Returns:
        None.

    Raises:
        None.
    """
    try:
        scheduler.add_job(
            func,
            "date",
            id=job_id,
            replace_existing=True,
            misfire_grace_time=None,
        )
        logger.info(f"Scheduled one-shot {description} job")
    except Exception as err:
        logger.error(f"Failed to schedule one-shot {description} job: {type(err).__name__}", exc_info=err)


def _scheduler_job_id(description: str) -> str:
    """
    Build a stable scheduler job ID from its description.

    Args:
        description: Human-readable job description.

    Returns:
        Stable APScheduler job identifier.

    Raises:
        None.
    """
    return "endurain_" + "_".join(description.lower().split())


def add_scheduler_job(
    func: Callable[..., object],
    interval: str,
    minutes: int,
    args: Sequence[object],
    description: str,
) -> None:
    """
    Register or replace a recurring scheduler job.

    Args:
        func: Callable to execute.
        interval: APScheduler trigger name.
        minutes: Interval length in minutes.
        args: Positional arguments passed to func.
        description: Human-readable job description.

    Returns:
        None.

    Raises:
        None.
    """
    try:
        logger.info(f"Added scheduler job to {description} every {minutes} minutes")
        scheduler.add_job(
            func,
            interval,
            minutes=minutes,
            args=list(args),
            id=_scheduler_job_id(description),
            replace_existing=True,
        )
    except Exception as err:
        logger.error(f"Failed to add scheduler job to {description}: {type(err).__name__}", exc_info=err)


def stop_scheduler() -> None:
    """
    Stop the scheduler if it is running.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    if scheduler.running:
        scheduler.shutdown(wait=False)
