"""Per-sport aggregation of activity stats (distance, time, calories).

Split out of ``utils.py``: pure computation over already-serialized
``Activity`` schemas, used by the timeframe stats routes. No DB, no ORM.
"""

import core.logger as core_logger
import modules.activities.activity.schema as activities_schema

logger = core_logger.get_logger(__name__)


def calculate_activity_stats(
    activities: list[activities_schema.Activity],
) -> activities_schema.ActivityStats:
    """Aggregate distance (m), time (s), and calories per sport type.

    Args:
        activities: List of Activity schema objects for the timeframe.

    Returns:
        ActivityStats with per-sport distance, time, and calories totals.
    """
    stats = activities_schema.ActivityStats()

    if activities is None:
        return stats

    # Sport-type buckets: activity_type IDs → attribute name on ActivityStats
    _sport_buckets: list[tuple[list[int], str]] = [
        ([1, 2, 3, 34, 40], "run"),
        ([4, 5, 6, 7, 27, 28, 29, 35, 36], "bike"),
        ([8, 9], "swim"),
        ([11, 31], "walk"),
        ([12], "hike"),
        ([13], "rowing"),
        ([15, 16], "snow_ski"),
        ([17], "snowboard"),
        ([30], "windsurf"),
        ([32], "stand_up_paddleboarding"),
        ([33], "surfing"),
        ([42], "kayaking"),
        ([43], "sailing"),
        ([44], "snowshoeing"),
        ([45], "inline_skating"),
    ]

    try:
        for activity in activities:
            for type_ids, bucket_name in _sport_buckets:
                if activity.activity_type in type_ids:
                    bucket = getattr(stats, bucket_name)
                    bucket.distance += float(activity.distance or 0)
                    bucket.time += float(activity.total_timer_time or 0)
                    bucket.calories += float(activity.calories or 0)
                    break
    except (TypeError, ValueError, AttributeError) as err:
        logger.error(
            "Error calculating activity stats",
            exc_info=err,
            extra=core_logger.context(activity_count=len(activities)),
        )

    return stats
