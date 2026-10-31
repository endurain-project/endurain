"""Scheduled work owned by activity ingestion."""

import jasil.runtime as platform_runtime

import core.scheduler as core_scheduler
import modules.activities.activity_ingestion.service as activity_ingestion_service

# One scheduler replica runs each pass; the jobs a pass queues are claimed by any worker. The scheduler
# takes the lock, so the services run bare and a replica that does not hold it skips the pass.
REFRESH_FANOUT_LOCK_NAME = "activity_ingestion_scheduled_refresh"
DEFERRED_REDISPATCH_LOCK_NAME = "activity_ingestion_deferred_refresh"
PRUNE_LOCK_NAME = "activity_ingestion_jobs_prune"
STALE_JOBS_LOCK_NAME = "activity_ingestion_jobs_fail_stale"
STAGED_SWEEP_LOCK_NAME = "activity_ingestion_staged_blob_sweep"


def prune_expired_ingestion_jobs() -> None:
    """Delete ingestion job rows beyond their retention window.

    Scheduler-invoked, with no request to carry the providers, so this entry
    point resolves them.
    """
    platform = platform_runtime.get_active_platform()
    activity_ingestion_service.prune_expired_ingestion_jobs(platform.clock)


def enqueue_provider_refreshes() -> None:
    """Queue a refresh job for every user who has linked a provider.

    Scheduler-invoked, with no request to carry the providers, so this entry
    point resolves them.
    """
    platform = platform_runtime.get_active_platform()
    activity_ingestion_service.enqueue_scheduled_refreshes(platform.storage)


def redispatch_deferred_refreshes() -> None:
    """Queue again the provider refreshes whose rate limit has cleared.

    Scheduler-invoked, with no request to carry the providers, so this entry
    point resolves them.
    """
    platform = platform_runtime.get_active_platform()
    activity_ingestion_service.redispatch_deferred_refreshes(platform.storage)


def fail_orphaned_local_refreshes() -> None:
    """Fail the refreshes a restart cost the in-process pool, before the startup fan-out queues new ones."""
    activity_ingestion_service.fail_orphaned_local_refreshes()


def schedule_provider_refresh() -> None:
    """Queue one provider refresh fan-out, so a restart catches up on what it missed."""
    core_scheduler.run_once(
        enqueue_provider_refreshes,
        job_id="endurain_provider_refresh_oneshot",
        description="provider refresh fan-out",
        lock_name=REFRESH_FANOUT_LOCK_NAME,
    )


def fail_stale_ingestion_jobs() -> None:
    """Fail ingestion jobs that stopped progressing.

    Scheduler-invoked, with no request to carry the providers, so this entry
    point resolves them.
    """
    platform = platform_runtime.get_active_platform()
    activity_ingestion_service.fail_stale_ingestion_jobs(platform.clock, platform.storage)


def sweep_stale_staged_blobs() -> None:
    """Delete staged ingestion blobs that nothing will read again.

    Scheduler-invoked, with no request to carry the providers, so this entry
    point resolves them.
    """
    platform = platform_runtime.get_active_platform()
    activity_ingestion_service.sweep_stale_staged_blobs(platform.clock, platform.storage)


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return ingestion retention and stale-job jobs.

    Returns:
        The jobs to schedule.
    """
    return (
        core_scheduler.ScheduledJob(
            prune_expired_ingestion_jobs,
            1440,
            "prune expired activity ingestion jobs",
            lock_name=PRUNE_LOCK_NAME,
        ),
        core_scheduler.ScheduledJob(
            enqueue_provider_refreshes,
            60,
            "queue a refresh for every user with a linked provider",
            lock_name=REFRESH_FANOUT_LOCK_NAME,
        ),
        core_scheduler.ScheduledJob(
            redispatch_deferred_refreshes,
            5,
            "queue again provider refreshes whose rate limit cleared",
            lock_name=DEFERRED_REDISPATCH_LOCK_NAME,
        ),
        core_scheduler.ScheduledJob(
            fail_stale_ingestion_jobs,
            60,
            "fail activity ingestion jobs that stopped progressing",
            lock_name=STALE_JOBS_LOCK_NAME,
        ),
        core_scheduler.ScheduledJob(
            sweep_stale_staged_blobs,
            1440,
            "remove staged ingestion blobs nothing will read",
            lock_name=STAGED_SWEEP_LOCK_NAME,
        ),
    )
