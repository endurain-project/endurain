"""Scheduled work owned by the activity-geocoding package."""

import core.scheduler as core_scheduler
import modules.activities.activity_geocoding.integration_service as geocoding_integration


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return geocoding reconciliation jobs."""
    return (
        core_scheduler.ScheduledJob(
            geocoding_integration.run_missing_location_backfill,
            60,
            "backfill missing activity locations (reverse-geocoding)",
        ),
    )


def schedule_missing_location_backfill() -> None:
    """Queue one missing-location reconciliation pass."""
    core_scheduler.run_once(
        geocoding_integration.run_missing_location_backfill,
        job_id="endurain_backfill_missing_locations_oneshot",
        description="activity-location backfill",
    )
