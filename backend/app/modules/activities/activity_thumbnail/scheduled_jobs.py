"""Scheduled work owned by the activity-thumbnail package."""

import jasil.runtime as platform_runtime

import core.database as core_database
import core.scheduler as core_scheduler
import modules.activities.activity_thumbnail.service as activity_thumbnail_service

SWEEP_LOCK_NAME = "thumbnail_sweep"
# Not the pass's own BACKFILL_LOCK_NAME: the in-process subscriber can start before the scheduler
# releases this lock, and would find its own lock held.
BACKFILL_REQUEST_LOCK_NAME = "thumbnail_backfill_request"


def request_thumbnail_backfill() -> None:
    """Ask for one pass that renders the thumbnails still missing.

    Scheduler-invoked, with no request to carry the clock or a session, so this entry point resolves the
    clock and opens the session. It renders nothing: a subscriber of the request runs the pass, off the API
    process when durable jobs are on.
    """
    platform = platform_runtime.get_active_platform()
    with core_database.SessionLocal() as db:
        activity_thumbnail_service.request_missing_thumbnail_backfill(platform.clock.now(), db)


def regenerate_all_thumbnails() -> None:
    """Delete and regenerate every activity thumbnail.

    Not run under the scheduler's lock: a regeneration that finds the backfill running must be retried,
    not skipped, so the service takes its backfill lock itself and reports a conflict.
    """
    platform = platform_runtime.get_active_platform()
    with core_database.SessionLocal() as db:
        activity_thumbnail_service.delete_and_regenerate_all_activity_thumbnails(
            platform.storage, platform.lock, platform.clock, db
        )


def sweep_orphaned_thumbnails() -> None:
    """Delete thumbnail blobs whose activity no longer exists.

    The storage-side net for the cleanup subscriber. Scheduler-invoked, so this
    entry point resolves the provider; the scheduler's lock keeps it to one replica.
    """
    platform = platform_runtime.get_active_platform()
    activity_thumbnail_service.sweep_orphaned_thumbnails(platform.storage)


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return thumbnail reconciliation jobs.

    Returns:
        The jobs to schedule.
    """
    return (
        core_scheduler.ScheduledJob(
            request_thumbnail_backfill,
            60,
            "request a pass that generates the missing thumbnails",
            lock_name=BACKFILL_REQUEST_LOCK_NAME,
        ),
        core_scheduler.ScheduledJob(
            sweep_orphaned_thumbnails,
            1440,
            "remove thumbnails whose activity is gone",
            lock_name=SWEEP_LOCK_NAME,
        ),
    )


def schedule_missing_thumbnail_generation() -> None:
    """Queue one request for a thumbnail backfill pass."""
    core_scheduler.run_once(
        request_thumbnail_backfill,
        job_id="endurain_generate_missing_thumbnails_oneshot",
        description="missing thumbnail generation request",
        lock_name=BACKFILL_REQUEST_LOCK_NAME,
    )


def schedule_full_thumbnail_regeneration() -> None:
    """Queue a delete-and-regenerate pass for every activity thumbnail."""
    core_scheduler.run_once(
        regenerate_all_thumbnails,
        job_id="endurain_regenerate_all_thumbnails",
        description="thumbnail regeneration",
    )
