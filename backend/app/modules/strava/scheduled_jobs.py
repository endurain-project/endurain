"""The Strava module's scheduled work, declared by the module that owns it.

Token refresh and the hourly pull of the last day's activities. Declared here so
the composition root can collect it without ``core.scheduler`` importing a
provider.
"""

import core.scheduler as core_scheduler
import modules.strava.activity_utils as strava_activity_utils
import modules.strava.utils as strava_utils


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """
    Return the Strava module's recurring scheduled jobs.

    Args:
        None.

    Returns:
        The module's scheduled jobs, for the composition root to register.

    Raises:
        None.
    """
    return (
        core_scheduler.ScheduledJob(
            strava_utils.refresh_strava_tokens,
            60,
            "refresh Strava user tokens every 60 minutes",
            [True],
        ),
        core_scheduler.ScheduledJob(
            strava_activity_utils.retrieve_strava_users_activities_for_days,
            60,
            "retrieve last day Strava users activities",
            [1, True],
        ),
    )
