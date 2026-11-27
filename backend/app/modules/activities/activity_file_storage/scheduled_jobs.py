"""Scheduled work owned by the activity-file-storage package."""

import jasil.runtime as platform_runtime

import core.blob_sweep as core_blob_sweep
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_file_storage.files as activity_file_storage_files
import modules.activities.activity_file_storage.service as activity_file_storage_service

logger = core_logger.get_logger(__name__)

SWEEP_LOCK_NAME = "activity_file_sweep"


def sweep_orphaned_activity_files() -> None:
    """Resolve the retained source files a crash or a lost event left behind.

    The net for the cleanup subscriber. The row sweep is a database query: it deletes the files of crashed uploads
    and of activities whose deletion event was lost, and finishes the deletions that failed. A second pass lists the
    ``processed/`` prefix, the files stored before rows existed, and deletes those whose activity is gone.
    Scheduler-invoked, with no request to carry the provider, so this entry point resolves it; the scheduler's lock
    keeps it to one replica.
    """
    storage = platform_runtime.get_active_platform().storage
    removed_files = activity_file_storage_service.sweep(storage)
    removed_legacy = core_blob_sweep.sweep_orphaned_blobs(
        storage,
        activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA,
        activity_integration.filter_existing_activity_ids,
        activity_file_storage_files.activity_id_of_processed_key,
        prefix="processed/",
    )
    if removed_files or removed_legacy:
        logger.info(
            "Removed orphaned activity source files",
            extra=core_logger.context(removed=removed_files, removed_legacy=removed_legacy),
        )


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return the retained-file reconciliation jobs.

    Returns:
        The jobs to schedule.
    """
    return (
        core_scheduler.ScheduledJob(
            sweep_orphaned_activity_files,
            1440,
            "remove retained activity source files nothing references",
            lock_name=SWEEP_LOCK_NAME,
        ),
    )
