"""Scheduled work owned by the health records."""

import core.database as core_database
import core.scheduler as core_scheduler
import modules.health.record_service as health_record_service

PRUNE_LOCK_NAME = "health_record_deletions_prune"


def prune_record_deletions() -> None:
    """Delete the tombstones of health records deleted longer ago than the sync retention."""
    with core_database.SessionLocal() as db:
        health_record_service.prune_deletions(db)


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return the health records' recurring scheduled jobs.

    Returns:
        The module's scheduled jobs, for the composition root to register.
    """
    return (
        core_scheduler.ScheduledJob(
            prune_record_deletions,
            24 * 60,
            "prune deleted health record tombstones past the sync retention",
            lock_name=PRUNE_LOCK_NAME,
        ),
    )
