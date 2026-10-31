"""Per-sport aggregation of activity stats (distance, time, calories).

Pure computation over the per-activity-type totals the database has already added up, used by the
timeframe stats routes. No DB, no ORM.
"""

from collections.abc import Iterable

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.schema as activity_schema

# Reversed once at import so each activity type is bucketed by a dict lookup rather
# than a scan of every sport's id list.
_SPORT_BY_ACTIVITY_TYPE: dict[int, str] = {
    activity_type: sport
    for sport, activity_types in activity_constants.ACTIVITY_TYPES_BY_SPORT.items()
    for activity_type in activity_types
}


def calculate_activity_stats(
    totals: Iterable[activity_contracts.ActivityTypeTotals],
) -> activity_schema.ActivityStatsRead:
    """Group per-activity-type totals into distance (m), time (s) and calories per sport.

    Args:
        totals: The timeframe's totals, one per activity type.

    Returns:
        ActivityStatsRead with per-sport distance, time, and calories totals. An activity type that
        belongs to no sport is left out.
    """
    stats = activity_schema.ActivityStatsRead()
    for total in totals:
        sport = _SPORT_BY_ACTIVITY_TYPE.get(total.activity_type)
        if sport is None:
            continue
        bucket = getattr(stats, sport)
        bucket.distance += total.distance
        bucket.time += total.time
        bucket.calories += total.calories
    return stats
