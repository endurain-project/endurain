"""The Garmin Connect module's scheduled work, declared by the module that owns it.

The four-hourly health-stats pull. The activity pull is one refresh job per
linked user, queued by activity ingestion. Declared here so the composition root
can collect it without ``core.scheduler`` importing a provider.
"""

import core.scheduler as core_scheduler
import modules.garmin.health_service as garmin_health_service

HEALTH_SYNC_LOCK = "garmin_health_sync"


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
            garmin_health_service.retrieve_recent_health,
            240,
            "retrieve last day Garmin Connect users health data",
            lock_name=HEALTH_SYNC_LOCK,
        ),
    )


def schedule_recent_health() -> None:
    """Queue one backfill of the last day of Garmin Connect health stats.

    It runs under the recurring pull's lock, so a restart of several replicas
    pulls once and startup never waits on Garmin round trips.
    """
    core_scheduler.run_once(
        garmin_health_service.retrieve_recent_health,
        job_id="endurain_garmin_recent_health_oneshot",
        description="recent Garmin Connect health pull",
        lock_name=HEALTH_SYNC_LOCK,
    )
