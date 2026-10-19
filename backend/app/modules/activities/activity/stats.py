"""Per-sport aggregation of activity stats (distance, time, calories).

Pure computation over already-serialized ``Activity`` schemas, used by the
timeframe stats routes. No DB, no ORM.
"""

import core.logger as core_logger
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.schema as activity_schema

logger = core_logger.get_logger(__name__)

# Reversed once at import so each activity is bucketed by a dict lookup rather
# than a scan of every sport's id list.
_SPORT_BY_ACTIVITY_TYPE: dict[int, str] = {
    activity_type: sport
    for sport, activity_types in activity_constants.ACTIVITY_TYPES_BY_SPORT.items()
    for activity_type in activity_types
}


def calculate_activity_stats(
    activities: list[activity_schema.ActivityRead],
) -> activity_schema.ActivityStatsRead:
    """Aggregate distance (m), time (s), and calories per sport type.

    Args:
        activities: List of Activity schema objects for the timeframe.

    Returns:
        ActivityStatsRead with per-sport distance, time, and calories totals.
    """
    stats = activity_schema.ActivityStatsRead()

    if activities is None:
        return stats

    try:
        for activity in activities:
            sport = _SPORT_BY_ACTIVITY_TYPE.get(activity.activity_type)
            if sport is None:
                continue
            bucket = getattr(stats, sport)
            bucket.distance += float(activity.distance or 0)
            bucket.time += float(activity.total_timer_time or 0)
            bucket.calories += float(activity.calories or 0)
    except (TypeError, ValueError, AttributeError) as err:
        logger.error(
            "Error calculating activity stats",
            exc_info=err,
            extra=core_logger.context(activity_count=len(activities)),
        )

    return stats
