"""Scheduled work owned by the activity-geocoding package."""

import jasil.runtime as platform_runtime

import core.database as core_database
import core.scheduler as core_scheduler
import modules.activities.activity_geocoding.service as activity_geocoding_service

BACKFILL_LOCK_NAME = "location_backfill"


def run_missing_location_backfill() -> None:
    """Scheduled reconciliation net: geocode GPS activities missing a location.

    Scheduler-invoked, with no request to carry the provider or a session, so
    this entry point resolves the provider and opens the session; the scheduler's
    lock keeps it to one replica.
    """
    platform = platform_runtime.get_active_platform()
    with core_database.SessionLocal() as db:
        activity_geocoding_service.backfill_missing_activity_locations(platform.geocoding, platform.clock, db)


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return geocoding reconciliation jobs.

    Returns:
        The jobs to schedule.
    """
    return (
        core_scheduler.ScheduledJob(
            run_missing_location_backfill,
            60,
            "backfill missing activity locations (reverse-geocoding)",
            lock_name=BACKFILL_LOCK_NAME,
        ),
    )


def schedule_missing_location_backfill() -> None:
    """Queue one missing-location reconciliation pass."""
    core_scheduler.run_once(
        run_missing_location_backfill,
        job_id="endurain_backfill_missing_locations_oneshot",
        description="activity-location backfill",
        lock_name=BACKFILL_LOCK_NAME,
    )
