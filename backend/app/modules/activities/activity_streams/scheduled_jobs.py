"""Scheduled work owned by the activity-streams package."""

import core.scheduler as core_scheduler
import modules.activities.activity_streams.integration_service as streams_integration


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return stream reconciliation jobs."""
    return (
        core_scheduler.ScheduledJob(
            streams_integration.run_missing_hr_zone_backfill,
            60,
            "backfill missing HR zone percentages",
        ),
    )


def schedule_missing_hr_zone_backfill() -> None:
    """Queue one missing-HR-zone reconciliation pass."""
    core_scheduler.run_once(
        streams_integration.run_missing_hr_zone_backfill,
        job_id="endurain_backfill_missing_hr_zones_oneshot",
        description="HR-zone backfill",
    )
