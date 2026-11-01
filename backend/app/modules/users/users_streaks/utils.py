"""Pure helpers for weekly streak calculation (no database access)."""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import core.calendar as core_calendar
import core.timezone as core_timezone

DEFAULT_RECENT_WEEKS = 12
"""Number of weeks returned in the streak history strip."""

_ONE_WEEK = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class StreakResult:
    """
    Result of a streak calculation.

    Attributes:
        current_streak: Consecutive met weeks up to now.
        current_streak_start: First week of the current streak.
        longest_streak: Longest run of consecutive met weeks.
        longest_streak_start: First week of the longest run.
        longest_streak_end: Last week of the longest run.
        current_week_count: Activities counted this week.
        current_week_met: Whether this week's target is met.
        at_risk: Streak running but this week not met yet.
        recent_weeks: (week_start, count, met) tuples, oldest
            first, ending with the current week.
    """

    current_streak: int
    current_streak_start: date | None
    longest_streak: int
    longest_streak_start: date | None
    longest_streak_end: date | None
    current_week_count: int
    current_week_met: bool
    at_risk: bool
    recent_weeks: list[tuple[date, int, bool]]


@lru_cache(maxsize=256)
def _resolve_timezone(tz_name: str | None) -> tzinfo:
    """
    Resolve an activity timezone string to a tzinfo.

    Activity timezones are usually IANA names, but some
    importers store values such as ``"(GMT+01:00) Europe/Zurich"``;
    the last whitespace-separated token is tried as a fallback.

    Args:
        tz_name: Timezone string stored on the activity.

    Returns:
        The resolved timezone, or UTC when unknown.
    """
    if not tz_name:
        return UTC
    for candidate in (tz_name.strip(), tz_name.strip().split(" ")[-1]):
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return UTC


def local_start_date(start_time: datetime | str | None, tz_name: str | None) -> date | None:
    """
    Return the local calendar date an activity started on.

    Args:
        start_time: Activity start (aware, naive UTC, ISO string or None).
        tz_name: Activity timezone name, if known.

    Returns:
        Local start date, or None if start_time is unusable.
    """
    aware = core_timezone.to_utc_aware(start_time)
    if aware is None:
        return None
    return aware.astimezone(_resolve_timezone(tz_name)).date()


def bucket_activities_by_week(
    activity_dates: Iterable[date],
    first_day_of_week: core_calendar.WeekdayValue,
) -> Counter[date]:
    """
    Count activities per week.

    Args:
        activity_dates: Local start date of each activity.
        first_day_of_week: User's configured first weekday.

    Returns:
        Mapping of week start date to activity count.
    """
    return Counter(core_calendar.get_week_start(day, first_day_of_week) for day in activity_dates)


def calculate_weekly_streak(
    week_counts: Mapping[date, int],
    current_week_start: date,
    min_activities_per_week: int,
    recent_weeks: int = DEFAULT_RECENT_WEEKS,
) -> StreakResult:
    """
    Calculate current and longest weekly streaks.

    A week is "met" when its count reaches the target. The
    current week only extends the streak once it is met; while
    it is not, the streak is measured up to the previous week
    and flagged as at risk. Weeks after the current week (e.g.
    from bad device clocks) are ignored.

    Args:
        week_counts: Activities per week start date.
        current_week_start: Start of the current week.
        min_activities_per_week: Weekly target (>= 1).
        recent_weeks: Number of history weeks to return.

    Returns:
        The calculated streak result.
    """
    target = max(1, min_activities_per_week)
    met_weeks = sorted(week for week, count in week_counts.items() if count >= target and week <= current_week_start)
    met_set = set(met_weeks)

    # Longest run; on ties keep the most recent run.
    longest = 0
    longest_start: date | None = None
    longest_end: date | None = None
    run_length = 0
    run_start: date | None = None
    previous: date | None = None
    for week in met_weeks:
        if previous is not None and week - previous == _ONE_WEEK:
            run_length += 1
        else:
            run_length = 1
            run_start = week
        if run_length >= longest:
            longest = run_length
            longest_start = run_start
            longest_end = week
        previous = week

    # Current run, anchored on this week if met, else last week.
    current_week_count = int(week_counts.get(current_week_start, 0))
    current_week_met = current_week_start in met_set
    anchor = current_week_start if current_week_met else current_week_start - _ONE_WEEK
    current = 0
    current_start: date | None = None
    while anchor in met_set:
        current += 1
        current_start = anchor
        anchor -= _ONE_WEEK

    history: list[tuple[date, int, bool]] = []
    for offset in range(max(1, recent_weeks) - 1, -1, -1):
        week = current_week_start - _ONE_WEEK * offset
        history.append((week, int(week_counts.get(week, 0)), week in met_set))

    return StreakResult(
        current_streak=current,
        current_streak_start=current_start,
        longest_streak=longest,
        longest_streak_start=longest_start,
        longest_streak_end=longest_end,
        current_week_count=current_week_count,
        current_week_met=current_week_met,
        at_risk=current > 0 and not current_week_met,
        recent_weeks=history,
    )
