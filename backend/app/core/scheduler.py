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
import time
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field

import jasil.retention as platform_retention
import jasil.runtime as platform_runtime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from jasil.providers import StateBackendUnavailableError

import core.logger as core_logger
import core.network as core_network

logger = core_logger.get_logger(__name__)

scheduler = AsyncIOScheduler()

#: How much of its interval, counted from the start of a run, a successful run of a locked job marks as done.
#: Each replica's scheduler fires its own interval, so another replica's tick inside the mark skips, and the mark
#: has expired by the time this replica's own next tick comes round.
_DUE_MARK_FRACTION = 0.9


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


@contextmanager
def _held_lock(lock_name: str) -> Generator[bool]:
    """Try to take a distributed lock, logging when another replica holds it.

    Args:
        lock_name: Stable coordination-lock name.

    Yields:
        ``True`` when the lock is held for the duration of the block, ``False`` when another replica holds it.
    """
    with platform_runtime.get_active_platform().lock.try_acquire(lock_name) as acquired:
        if not acquired:
            logger.debug(
                "Scheduler job skipped because another replica holds its lock",
                extra=core_logger.context(lock_name=lock_name),
            )
        yield acquired


def run_locked_job(lock_name: str, func: Callable[..., object], *args: object) -> object | None:
    """Run a synchronous scheduled job only while holding its distributed lock.

    Args:
        lock_name: Stable coordination-lock name.
        func: Scheduled operation to run.
        *args: Positional arguments forwarded to the operation.

    Returns:
        The operation result, or ``None`` when another replica holds the lock.
    """
    with _held_lock(lock_name) as acquired:
        return func(*args) if acquired else None


def _mark_key(lock_name: str) -> str:
    """Build the state key that marks a locked job as run this interval.

    Args:
        lock_name: Stable coordination-lock name, which also names the mark.

    Returns:
        The state key.
    """
    return f"endurain:scheduler:last-run:{lock_name}"


def _is_due(lock_name: str) -> bool:
    """Check, under the job's lock, whether another replica already ran a locked job this interval.

    The lock only keeps two runs from overlapping; without the mark, every replica would run the job once
    per interval of its own. An unreachable state store lets the run go ahead, still under its lock.

    Args:
        lock_name: Stable coordination-lock name, which also names the mark.

    Returns:
        True when this run is due, False when another replica ran the job this interval.
    """
    try:
        marked = platform_runtime.get_active_platform().state.get(_mark_key(lock_name)) is not None
    except StateBackendUnavailableError as err:
        logger.warning(
            "Could not read whether a scheduler job ran; running it under its lock",
            exc_info=err,
            extra=core_logger.context(lock_name=lock_name),
        )
        return True
    if marked:
        logger.debug(
            "Scheduler job skipped because another replica already ran it this interval",
            extra=core_logger.context(lock_name=lock_name),
        )
    return not marked


def _mark_run(lock_name: str, minutes: int, started: float) -> None:
    """Mark a locked job as run for the rest of this interval, after a run that succeeded.

    Only a finished run is marked, so a run that raised, or a replica that died mid-run, leaves the job due at
    the next tick of any replica. The mark lasts until a fixed share of the interval after the run started; a
    run that took longer leaves no mark.

    Args:
        lock_name: Stable coordination-lock name, which also names the mark.
        minutes: The job's interval.
        started: ``time.monotonic()`` when the run started.
    """
    ttl_seconds = int(minutes * 60 * _DUE_MARK_FRACTION - (time.monotonic() - started))
    if ttl_seconds < 1:
        return
    try:
        platform_runtime.get_active_platform().state.set(_mark_key(lock_name), b"1", ttl_seconds=ttl_seconds)
    except StateBackendUnavailableError as err:
        logger.warning(
            "Could not mark a scheduler job as run; another replica may run it again this interval",
            exc_info=err,
            extra=core_logger.context(lock_name=lock_name),
        )


def run_due_job(lock_name: str, minutes: int, func: Callable[..., object], *args: object) -> object | None:
    """Run a synchronous recurring job once per interval across every replica, retrying a failed run.

    The lock is held across the check, the run and the mark, so two replicas never run the job at once.

    Args:
        lock_name: Stable coordination-lock name.
        minutes: The job's interval.
        func: Scheduled operation to run.
        *args: Positional arguments forwarded to the operation.

    Returns:
        The operation result, or ``None`` when another replica holds the lock or already ran the job.
    """
    with _held_lock(lock_name) as acquired:
        if not acquired or not _is_due(lock_name):
            return None
        started = time.monotonic()
        result = func(*args)
        _mark_run(lock_name, minutes, started)
        return result


async def _run_due_async_job(lock_name: str, minutes: int, func: Callable[..., object], *args: object) -> object | None:
    """Run an asynchronous recurring job once per interval across every replica, retrying a failed run.

    The lock is held across the check, the run and the mark, so two replicas never run the job at once.

    Args:
        lock_name: Stable coordination-lock name.
        minutes: The job's interval.
        func: Scheduled coroutine function to run.
        *args: Positional arguments forwarded to the operation.

    Returns:
        The awaited result, or ``None`` when another replica holds the lock or already ran the job.
    """
    with _held_lock(lock_name) as acquired:
        if not acquired or not _is_due(lock_name):
            return None
        started = time.monotonic()
        result = func(*args)
        if inspect.isawaitable(result):
            result = await result
        _mark_run(lock_name, minutes, started)
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
            func = _run_due_async_job if inspect.iscoroutinefunction(job.func) else run_due_job
            args = (job.lock_name, job.minutes, job.func, *job.args)
        add_scheduler_job(func, "interval", job.minutes, args, job.description)

    # Clears any backlog promptly, so a frequently-restarted deployment does not
    # starve the daily prune declared in platform_jobs().
    run_once(
        platform_retention.prune_expired_records,
        job_id="endurain_prune_expired_records_oneshot",
        description="retention prune",
    )


def run_once(func: Callable[..., object], *, job_id: str, description: str, lock_name: str | None = None) -> None:
    """
    Queue a one-shot job on the scheduler's own executor.

    Args:
        func: Callable to execute once.
        job_id: Fixed APScheduler job ID, so repeated calls coalesce into a
            single pending run.
        description: Human-readable description, used in log messages.
        lock_name: Distributed lock the run must hold, or ``None`` when every
            replica may run it.

    Returns:
        None.

    Raises:
        None.
    """
    args: tuple[object, ...] = ()
    if lock_name is not None:
        func, args = run_locked_job, (lock_name, func)
    try:
        scheduler.add_job(
            func,
            "date",
            args=args,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=None,
        )
        logger.info("Scheduled a one-shot job", extra=core_logger.context(description=description))
    except Exception as err:
        logger.error(
            "Failed to schedule a one-shot job", exc_info=err, extra=core_logger.context(description=description)
        )


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
        logger.info("Added a scheduler job", extra=core_logger.context(description=description, minutes=minutes))
        scheduler.add_job(
            func,
            interval,
            minutes=minutes,
            args=list(args),
            id=_scheduler_job_id(description),
            replace_existing=True,
        )
    except Exception as err:
        logger.error("Failed to add a scheduler job", exc_info=err, extra=core_logger.context(description=description))


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
