"""Weekly streak calculation over a user's activities."""

from datetime import date

from sqlalchemy.orm import Session

import core.calendar as core_calendar
import modules.activities.activity.integration_service as activity_integration
import modules.users.users_streak_settings.schema as streak_settings_schema
import modules.users.users_streaks.schema as streak_schema
import modules.users.users_streaks.utils as streak_utils


def get_weekly_streak(
    user_id: int,
    first_day_of_week: core_calendar.WeekdayValue,
    settings: streak_settings_schema.UsersStreakSettingsBase,
    today: date,
    db: Session,
) -> streak_schema.WeeklyStreakResponse:
    """
    Calculate the weekly streak for a user.

    Hidden activities are skipped so a duplicate import from a
    second source cannot count twice. Activities are bucketed by
    their local start date, so a late Sunday evening run counts
    for the right week regardless of the UTC offset.

    Args:
        user_id: Target user ID.
        first_day_of_week: User's configured first weekday.
        settings: Streak settings (target and type filter).
        today: The user's local date.
        db: Database session.

    Returns:
        The weekly streak response.
    """
    activity_types = settings.activity_types or None
    local_dates = [
        local_date
        for activity in activity_integration.list_user_activity_starts(user_id, db, activity_types=activity_types)
        if (local_date := streak_utils.local_start_date(activity.start_time, activity.timezone)) is not None
    ]

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
