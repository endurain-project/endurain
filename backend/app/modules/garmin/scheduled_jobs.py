"""The Garmin Connect module's scheduled work, declared by the module that owns it.

The hourly activity pull and the four-hourly health-stats pull. Declared here so
the composition root can collect it without ``core.scheduler`` importing a
provider.
"""

import core.scheduler as core_scheduler
import modules.garmin.activity_utils as garmin_activity_utils
import modules.garmin.health_utils as garmin_health_utils


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """
    Return the Garmin Connect module's recurring scheduled jobs.

    Args:
        None.

    Returns:
        The module's scheduled jobs, for the composition root to register.

    Raises:
        None.
    """
    return (
        core_scheduler.ScheduledJob(
            garmin_activity_utils.retrieve_garminconnect_users_activities_for_days,
            60,
            "retrieve last day Garmin Connect users activities",
            [1],
        ),
        core_scheduler.ScheduledJob(
            garmin_health_utils.retrieve_garminconnect_users_health_for_days,
            240,
            "retrieve last day Garmin Connect users health data",
            [1],
        ),
    )
