"""Scheduled work owned by the activity-thumbnail package."""

import jasil.runtime as platform_runtime

import core.database as core_database
import core.scheduler as core_scheduler
import modules.activities.activity_thumbnail.service as activity_thumbnail_service


def generate_missing_thumbnails() -> None:
    """Generate thumbnails for activities whose stored key is missing.

    Scheduler-invoked, with no request to carry the providers or a session, so
    this entry point resolves the providers and opens the session.
    """
    platform = platform_runtime.get_active_platform()
    with core_database.SessionLocal() as db:
        activity_thumbnail_service.generate_missing_activity_thumbnails(
            platform.storage, platform.lock, platform.clock, db
        )


def regenerate_all_thumbnails() -> None:
    """Delete and regenerate every activity thumbnail."""
    platform = platform_runtime.get_active_platform()
    with core_database.SessionLocal() as db:
        activity_thumbnail_service.delete_and_regenerate_all_activity_thumbnails(
            platform.storage, platform.lock, platform.clock, db
        )


def sweep_orphaned_thumbnails() -> None:
    """Delete thumbnail blobs whose activity no longer exists.

    The storage-side net for the cleanup subscriber. Scheduler-invoked, so this
    entry point resolves the providers and opens the session.
    """
    platform = platform_runtime.get_active_platform()
    with platform.lock.try_acquire("thumbnail_sweep") as acquired:
        if not acquired:
            return
        with core_database.SessionLocal() as db:
            activity_thumbnail_service.sweep_orphaned_thumbnails(platform.storage, db)


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return thumbnail reconciliation jobs.

    Returns:
        The jobs to schedule.
    """
    return (
        core_scheduler.ScheduledJob(
            generate_missing_thumbnails,
            60,
            "generate thumbnails for activities missing one",
        ),
        core_scheduler.ScheduledJob(
            sweep_orphaned_thumbnails,
            1440,
            "remove thumbnails whose activity is gone",
        ),
    )


def schedule_missing_thumbnail_generation() -> None:
    """Queue one thumbnail reconciliation pass."""
    core_scheduler.run_once(
        generate_missing_thumbnails,
        job_id="endurain_generate_missing_thumbnails_oneshot",
        description="missing thumbnail generation",
    )
