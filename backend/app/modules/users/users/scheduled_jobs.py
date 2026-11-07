"""Scheduled work owned by users."""

import jasil.runtime as platform_runtime

import core.scheduler as core_scheduler
import modules.users.users.constants as users_constants
import modules.users.users.deletion_job_service as users_deletion_job_service
import modules.users.users.deletion_state_store as users_deletion_state_store
import modules.users.users.photo_service as users_photo_service

DELETION_SWEEP_LOCK_NAME = "users_deletion_sweep"
PHOTO_SWEEP_LOCK_NAME = "users_photo_sweep"


def requeue_stalled_deletions() -> None:
    """Queue again the account deletions that never finished.

    Scheduler-invoked, with no request to carry the providers, so this entry point resolves them; the
    scheduler's lock keeps it to one replica.
    """
    platform = platform_runtime.get_active_platform()
    users_deletion_job_service.requeue_stalled_deletions(
        users_deletion_state_store.UserDeletionStateStore(platform.state), platform.storage, platform.clock
    )


def sweep_unreferenced_photos() -> None:
    """Delete photo blobs no user names any more.

    Scheduler-invoked, with no request to carry the provider, so this entry point resolves it; the
    scheduler's lock keeps it to one replica.
    """
    users_photo_service.sweep_unreferenced_photos(platform_runtime.get_active_platform().storage)


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return the account deletion and photo sweeps.

    Returns:
        The jobs to schedule.
    """
    return (
        core_scheduler.ScheduledJob(
            requeue_stalled_deletions,
            users_constants.DELETION_SWEEP_INTERVAL_MINUTES,
            "queue again account deletions that never finished",
            lock_name=DELETION_SWEEP_LOCK_NAME,
        ),
        core_scheduler.ScheduledJob(
            sweep_unreferenced_photos,
            users_constants.PHOTO_SWEEP_INTERVAL_MINUTES,
            "remove user photos no user names",
            lock_name=PHOTO_SWEEP_LOCK_NAME,
        ),
    )
