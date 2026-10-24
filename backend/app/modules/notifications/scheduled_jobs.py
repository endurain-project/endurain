"""Scheduled work owned by the notifications package."""

import core.database as core_database
import core.scheduler as core_scheduler
import modules.notifications.service as notifications_service

PURGE_LOCK_NAME = "notifications_purge"


def purge_read_notifications() -> None:
    """Delete read notifications past the retention period.

    Scheduler-invoked, with no request to carry a session, so this entry point opens
    its own; the scheduler's lock keeps it to one replica.
    """
    with core_database.SessionLocal() as db:
        notifications_service.purge_read_notifications(db)


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return the notification retention job.

    Returns:
        The jobs to schedule.
    """
    return (
        core_scheduler.ScheduledJob(
            purge_read_notifications,
            1440,
            "purge read notifications past the retention period",
            lock_name=PURGE_LOCK_NAME,
        ),
    )
