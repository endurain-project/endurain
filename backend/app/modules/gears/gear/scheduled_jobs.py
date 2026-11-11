"""Scheduled prune of the gear deletion records kept for incremental sync."""

from datetime import UTC, datetime

import core.database as core_database
import core.scheduler as core_scheduler
import modules.gears.gear.service as gears_service

PRUNE_LOCK_NAME = "gears_gear_deletions_prune"


def prune_gear_deletions() -> None:
    """Delete the gear deletion records older than the retention period."""
    with core_database.SessionLocal() as db:
        gears_service.prune_gear_deletions(datetime.now(UTC), db)


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return recurring gear deletion-record maintenance work."""
    return (
        core_scheduler.ScheduledJob(
            prune_gear_deletions,
            1440,
            "prune gear deletion records past the retention period",
            lock_name=PRUNE_LOCK_NAME,
        ),
    )
