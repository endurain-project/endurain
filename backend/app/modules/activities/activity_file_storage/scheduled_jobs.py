"""Scheduled work owned by the activity-file-storage package."""

import jasil.runtime as platform_runtime

import core.blob_sweep as core_blob_sweep
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_file_storage.files as activity_file_storage_files

logger = core_logger.get_logger(__name__)

SWEEP_LOCK_NAME = "activity_file_sweep"


def sweep_orphaned_activity_files() -> None:
    """Delete retained source files whose activity no longer exists.

    The storage-side net for the cleanup subscriber. The package has no
    ``service`` (it is a leaf over ``StorageProvider``), so the sweep is wired
    here. Scheduler-invoked, with no request to carry the provider, so this entry
    point resolves it; the scheduler's lock keeps it to one replica.
    """
    platform = platform_runtime.get_active_platform()
    removed = core_blob_sweep.sweep_orphaned_blobs(
        platform.storage,
        activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA,
        activity_integration.filter_existing_activity_ids,
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
            lock_name=SWEEP_LOCK_NAME,
        ),
    )
