"""Scheduled work owned by the activity-media package."""

import jasil.runtime as platform_runtime

import core.database as core_database
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.activities.activity_media.service as activity_media_service

logger = core_logger.get_logger(__name__)


def sweep_orphaned_media() -> None:
    """Delete media blobs whose activity no longer exists.

    The storage-side net for the cleanup subscriber. Scheduler-invoked, with no
    request to carry the provider or a session, so this entry point resolves the
    provider, opens the session and holds the coordination lock so only one
    replica runs the pass.
    """
    platform = platform_runtime.get_active_platform()
    with platform.lock.try_acquire("activity_media_sweep") as acquired:
        if not acquired:
            logger.debug("Activity-media sweep: another replica holds the lock; skipping")
            return
        with core_database.SessionLocal() as db:
            removed = activity_media_service.sweep_orphaned_media(platform.storage, db)
        if removed:
            logger.info("Removed orphaned activity media blobs", extra=core_logger.context(removed=removed))


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return the media reconciliation jobs.

    Returns:
        The jobs to schedule.
    """
    return (
        core_scheduler.ScheduledJob(
            sweep_orphaned_media,
            1440,
            "remove activity media blobs whose activity is gone",
        ),
    )
