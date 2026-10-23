"""The Garmin Connect module's scheduled work, declared by the module that owns it.

The four-hourly health-stats pull. The activity pull is one refresh job per
linked user, queued by activity ingestion. Declared here so the composition root
can collect it without ``core.scheduler`` importing a provider.
"""

import core.scheduler as core_scheduler
import modules.garmin.health_service as garmin_health_service


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return the Garmin Connect module's recurring scheduled jobs.

    Args:
        None.

    Returns:
        The module's scheduled jobs, for the composition root to register.

    Raises:
        None.
    """
    return (
        core_scheduler.ScheduledJob(
            garmin_health_service.retrieve_garminconnect_users_health_for_days,
            240,
            "retrieve last day Garmin Connect users health data",
            [1],
            "garmin_health_sync",
        ),
    )


def retrieve_recent_health() -> None:
    """Backfill the last day of Garmin Connect health stats for every user."""
    garmin_health_service.retrieve_garminconnect_users_health_for_days(1)
