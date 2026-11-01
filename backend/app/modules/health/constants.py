"""Constants for health-related modules."""

from enum import Enum

#: Times an upsert re-reads a day's record and applies again after another writer changed it first.
#: Each round lets at least one writer through, so this serves up to that many concurrent writers of one day.
UPSERT_ATTEMPTS = 5


class Interval(Enum):
    """Enumeration of time intervals for health weight data queries.

    Attributes:
        LAST_7_DAYS: Last 7 days interval.
        LAST_30_DAYS: Last 30 days interval.
        LAST_90_DAYS: Last 90 days interval.
        LAST_YEAR: Last year interval.
        ALL_TIME: All time interval.
    """

    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    LAST_90_DAYS = "last_90_days"
    LAST_YEAR = "last_year"
    ALL_TIME = "all_time"


class ChartBucket(Enum):
    """Calendar span one chart point aggregates.

    Attributes:
        DAY: One point per day.
        WEEK: One point per ISO week, dated its Monday.
        MONTH: One point per month, dated its first day.
    """

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


#: The buckets a chart may use, finest first. A chart is daily and coarsens only while it would exceed
#: ``MAX_CHART_POINTS``, so a daily metric stays daily for as long as the bars stay readable.
CHART_BUCKETS = (ChartBucket.DAY, ChartBucket.WEEK, ChartBucket.MONTH)

#: Most points a chart holds: a full year of daily bars, which is also a small response.
MAX_CHART_POINTS = 366
