"""Scheduled prune of the gear component deletion records kept for incremental sync."""

from datetime import UTC, datetime

import core.database as core_database
import core.scheduler as core_scheduler
import modules.gears.gear_components.service as gear_components_service

PRUNE_LOCK_NAME = "gears_gear_components_deletions_prune"


def prune_gear_component_deletions() -> None:
    """Delete the gear component deletion records older than the retention period."""
    with core_database.SessionLocal() as db:
        gear_components_service.prune_gear_component_deletions(datetime.now(UTC), db)


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return recurring gear component deletion-record maintenance work."""
    return (
        core_scheduler.ScheduledJob(
            prune_gear_component_deletions,
            1440,
            "prune gear component deletion records past the retention period",
            lock_name=PRUNE_LOCK_NAME,
        ),
    )
