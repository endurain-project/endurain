"""Database access for weekly streak calculation."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

import activities.activity_streaks.schema as streak_schema
import activities.activity_streaks.utils as streak_utils
import core.calendar as core_calendar
import core.decorators as core_decorators
import users.users_streak_settings.schema as streak_settings_schema
from activities.activity.models import Activity


@core_decorators.handle_db_errors
def get_weekly_streak(
    db: Session,
    user_id: int,
    first_day_of_week: core_calendar.WeekdayValue,
    settings: streak_settings_schema.UsersStreakSettingsBase,
    now: datetime | None = None,
) -> streak_schema.WeeklyStreakResponse:
    """
    Calculate the weekly streak for a user.

    Only the start time and timezone of each matching,
    non-hidden activity are loaded; weekly bucketing happens
    in Python on the activity's local start date so that,
    e.g., a late Sunday evening run counts for the right week
    regardless of the UTC offset. "Today" is taken in the
    timezone of the user's most recent activity.

    Args:
        db: Database session.
        user_id: Target user ID.
        first_day_of_week: User's configured first weekday.
        settings: Streak settings (target and type filter).
        now: Optional aware "now" for testing.

    Returns:
        The weekly streak response.

    Raises:
        HTTPException: 500 error if the database query fails.
    """
    stmt = (
        select(Activity.start_time, Activity.timezone)
        .where(
            Activity.user_id == user_id,
            Activity.is_hidden.is_(False),
        )
        .order_by(Activity.start_time.asc())
    )
    if settings.activity_types:
        stmt = stmt.where(Activity.activity_type.in_(settings.activity_types))

    rows = db.execute(stmt).all()

    local_dates = []
    latest_timezone: str | None = None
    for row in rows:
        local_date = streak_utils.local_start_date(row.start_time, row.timezone)
        if local_date is not None:
            local_dates.append(local_date)
        if row.timezone:
            latest_timezone = row.timezone

    today = streak_utils.today_for_timezone(latest_timezone, now)
    current_week_start = core_calendar.get_week_start(today, first_day_of_week)
    week_counts = streak_utils.bucket_activities_by_week(local_dates, first_day_of_week)

    result = streak_utils.calculate_weekly_streak(
        week_counts=week_counts,
        current_week_start=current_week_start,
        min_activities_per_week=settings.min_activities_per_week,
    )

    return streak_schema.WeeklyStreakResponse(
        current_streak=result.current_streak,
        current_streak_start=result.current_streak_start,
        longest_streak=result.longest_streak,
        longest_streak_start=result.longest_streak_start,
        longest_streak_end=result.longest_streak_end,
        current_week_start=current_week_start,
        current_week_count=result.current_week_count,
        current_week_met=result.current_week_met,
        at_risk=result.at_risk,
        min_activities_per_week=settings.min_activities_per_week,
        activity_types=settings.activity_types,
        recent_weeks=[
            streak_schema.StreakWeek(week_start=week, activity_count=count, met=met)
            for week, count, met in result.recent_weeks
        ],
    )
