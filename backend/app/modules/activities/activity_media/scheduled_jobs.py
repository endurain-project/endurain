"""Scheduled work owned by the activity-media package."""

import jasil.runtime as platform_runtime

import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.activities.activity_media.service as activity_media_service

logger = core_logger.get_logger(__name__)

SWEEP_LOCK_NAME = "activity_media_sweep"


def sweep_orphaned_media() -> None:
    """Delete media blobs whose activity no longer exists.

    The storage-side net for the cleanup subscriber. Scheduler-invoked, with no
    request to carry the provider, so this entry point resolves it; the scheduler's
    lock keeps it to one replica.
    """
    platform = platform_runtime.get_active_platform()
    removed = activity_media_service.sweep_orphaned_media(platform.storage)
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
            lock_name=SWEEP_LOCK_NAME,
        ),
    )
