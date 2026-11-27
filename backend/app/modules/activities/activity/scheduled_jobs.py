"""Scheduled work owned by the activity package."""

from datetime import UTC, datetime

import core.database as core_database
import core.scheduler as core_scheduler
import modules.activities.activity.service as activity_service

PRUNE_LOCK_NAME = "activity_deletions_prune"


def prune_activity_deletions() -> None:
    """Delete the activity tombstones older than the retention.

    Scheduler-invoked, so it opens its own session; the scheduler's lock keeps it to one replica.
    """
    with core_database.SessionLocal() as db:
        activity_service.prune_activity_deletions(datetime.now(UTC), db)


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return the activity tombstone prune job.

    Returns:
        The jobs to schedule.
    """
    return (
        core_scheduler.ScheduledJob(
            prune_activity_deletions,
            1440,
            "remove activity deletion tombstones past their retention",
            lock_name=PRUNE_LOCK_NAME,
        ),
    )
