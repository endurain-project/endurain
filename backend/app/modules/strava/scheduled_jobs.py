"""The Strava module's scheduled work, declared by the module that owns it.

Strava has none of its own any more: the hourly activity pull is one refresh job
per linked user, queued by activity ingestion, and each of those refreshes the
user's access token before it fetches. The function stays so the composition
root keeps collecting scheduled work from every provider the same way.
"""

import core.scheduler as core_scheduler


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """
    Return the Strava module's recurring scheduled jobs.

    Returns:
        The module's scheduled jobs, for the composition root to register.
    """
    return ()
