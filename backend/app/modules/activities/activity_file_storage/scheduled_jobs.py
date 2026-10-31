"""Scheduled work owned by the activity-file-storage package."""

import jasil.runtime as platform_runtime

import core.database as core_database
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_file_storage.files as activity_file_storage_files
import modules.activities.orphan_sweep as activities_orphan_sweep

logger = core_logger.get_logger(__name__)


def sweep_orphaned_activity_files() -> None:
    """Delete retained source files whose activity no longer exists.

    The storage-side net for the cleanup subscriber. The package has no
    ``service`` (it is a leaf over ``StorageProvider``), so the sweep is wired
    here. Scheduler-invoked, with no request to carry the provider or a session,
    so this entry point resolves the provider, opens the session and holds the
    coordination lock so only one replica runs the pass.
    """
    platform = platform_runtime.get_active_platform()
    with platform.lock.try_acquire("activity_file_sweep") as acquired:
        if not acquired:
            logger.debug("Activity-file sweep: another replica holds the lock; skipping")
            return
        with core_database.SessionLocal() as db:
            removed = activities_orphan_sweep.sweep_orphaned_blobs(
                platform.storage,
                activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA,
                lambda ids: activity_integration.filter_existing_activity_ids(ids, db),
                activity_file_storage_files.activity_id_of_processed_key,
                prefix="processed/",
            )
        if removed:
            logger.info("Removed orphaned activity source files", extra=core_logger.context(removed=removed))


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return the retained-file reconciliation jobs.

    Returns:
        The jobs to schedule.
    """
    return (
        core_scheduler.ScheduledJob(
            sweep_orphaned_activity_files,
            1440,
            "remove retained activity source files whose activity is gone",
        ),
    )
