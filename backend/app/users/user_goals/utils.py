"""User goals utility functions for progress calculation."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

import users.user_goals.schema as user_goals_schema
import users.user_goals.models as user_goals_models
import users.user_goals.crud as user_goals_crud

import activities.activity.crud as activity_crud
import core.logger as core_logger

_ACTIVITY_TYPE_MAP: dict[str, list[int]] = {
    user_goals_schema.ActivityType.RUN.value: [1, 2, 3, 34, 40],
    user_goals_schema.ActivityType.BIKE.value: [4, 5, 6, 7, 27, 28, 29, 35, 36],
    user_goals_schema.ActivityType.SWIM.value: [8, 9],
    user_goals_schema.ActivityType.WALK.value: [11, 12, 44],
    user_goals_schema.ActivityType.CARDIO.value: [20, 41, 46],
}

_DEFAULT_ACTIVITY_TYPES: list[int] = [10, 19]


def calculate_user_goals(
    user_id: int, date: str | None, db: Session
) -> list[user_goals_schema.UserGoalProgress] | None:
    """
    Calculate progress for all user goals on a specified date.

    Args:
        user_id: The ID of the user.
        date: Date in YYYY-MM-DD format. If None, uses
            current date.
        db: SQLAlchemy database session.

    Returns:
        List of UserGoalProgress objects, or None if no
            goals found.

    Raises:
        HTTPException: If database error occurs.
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        goals = user_goals_crud.get_user_goals_by_user_id(user_id, db)

        if not goals:
            return None

        return [
            calculate_goal_progress_by_activity_type(goal, date, db) for goal in goals
        ]
    except HTTPException as http_err:
        raise http_err
    except (ValueError, TypeError) as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in calculate_user_goals: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 400 status code
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid data provided",
        ) from err
    except Exception as err:
        # Log unexpected exceptions
        core_logger.print_to_log(
            f"Unexpected error in calculate_user_goals: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def calculate_goal_progress_by_activity_type(
    goal: user_goals_models.UserGoal,
    date: str,
    db: Session,
) -> user_goals_schema.UserGoalProgress:
    """
    Calculate goal progress for a specific activity type.

    Args:
        goal: User goal object with goal details.
        date: Reference date in YYYY-MM-DD format.
        db: SQLAlchemy database session.

    Returns:
        UserGoalProgress object with progress details.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        start_date, end_date = get_start_end_date_by_interval(goal.interval, date)

        # Get activity types based on goal.activity_type
        activity_types = _ACTIVITY_TYPE_MAP.get(
            goal.activity_type, _DEFAULT_ACTIVITY_TYPES
        )

        # Fetch all activities in a single query
        activities = activity_crud.get_user_activities_per_timeframe_and_activity_types(
            goal.user_id,
            activity_types,
            start_date,
            end_date,
            db,
            True,
        )

        # Calculate totals based on goal type
        percentage_completed = 0
        total_calories = 0
        total_activities_number = 0
        total_distance = 0
        total_elevation = 0
        total_duration = 0

        if activities:
            if goal.goal_type == user_goals_schema.GoalType.CALORIES:
                total_calories = sum(activity.calories or 0 for activity in activities)
                if goal.goal_calories and goal.goal_calories > 0:
                    percentage_completed = (total_calories / goal.goal_calories) * 100
            elif goal.goal_type == user_goals_schema.GoalType.DISTANCE:
                total_distance = sum(activity.distance or 0 for activity in activities)
                if goal.goal_distance and goal.goal_distance > 0:
                    percentage_completed = (total_distance / goal.goal_distance) * 100
            elif goal.goal_type == user_goals_schema.GoalType.ELEVATION:
                total_elevation = sum(
                    activity.elevation_gain or 0 for activity in activities
                )
                if goal.goal_elevation and goal.goal_elevation > 0:
                    percentage_completed = (total_elevation / goal.goal_elevation) * 100
            elif goal.goal_type == user_goals_schema.GoalType.DURATION:
                total_duration = sum(
                    activity.total_elapsed_time or 0 for activity in activities
                )
                if goal.goal_duration and goal.goal_duration > 0:
                    percentage_completed = (total_duration / goal.goal_duration) * 100
            elif goal.goal_type == user_goals_schema.GoalType.ACTIVITIES:
                total_activities_number = len(activities)
                if goal.goal_activities_number and goal.goal_activities_number > 0:
                    percentage_completed = (
                        total_activities_number / goal.goal_activities_number
                    ) * 100

        if percentage_completed > 100:
            percentage_completed = 100

        # Create and return the progress object
        return user_goals_schema.UserGoalProgress(
            goal_id=goal.id,
            interval=goal.interval,
            activity_type=goal.activity_type,
            goal_type=goal.goal_type,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            percentage_completed=round(percentage_completed),
            total_calories=total_calories,
            total_activities_number=total_activities_number,
            total_distance=round(total_distance),
            total_elevation=round(total_elevation),
            total_duration=total_duration,
            goal_calories=goal.goal_calories,
            goal_activities_number=goal.goal_activities_number,
            goal_distance=goal.goal_distance,
            goal_elevation=goal.goal_elevation,
            goal_duration=goal.goal_duration,
        )
    except HTTPException as http_err:
        raise http_err
    except (ValueError, TypeError) as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in calculate_goal_progress_by_activity_type: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 400 status code
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid data provided",
        ) from err
    except Exception as err:
        # Log unexpected exceptions
        core_logger.print_to_log(
            f"Unexpected error in calculate_goal_progress_by_activity_type: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_start_end_date_by_interval(
    interval: str, date: str
) -> tuple[datetime, datetime]:
    """
    Get start and end datetimes for interval containing date.

    Args:
        interval: One of yearly, monthly, weekly, or daily.
        date: Date string in YYYY-MM-DD format.

    Returns:
        Tuple of (start_date, end_date) datetimes.

    Raises:
        HTTPException: If invalid interval specified.
    """
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    if interval == "yearly":
        start_date = date_obj.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        # Calculate the last second of December 31st of the same year
        end_date = datetime(date_obj.year, 12, 31, 23, 59, 59)
    elif interval == "weekly":
        start_date = date_obj - timedelta(days=date_obj.weekday())  # Monday
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(
            days=6, hours=23, minutes=59, seconds=59
        )  # Sunday
    elif interval == "monthly":
        start_date = date_obj.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Get the first day of next month
        if date_obj.month == 12:
            next_month = start_date.replace(year=date_obj.year + 1, month=1)
        else:
            next_month = start_date.replace(month=date_obj.month + 1)
        # Subtract one second to get the last second of the current month
        end_date = next_month - timedelta(seconds=1)
    elif interval == "daily":
        start_date = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = date_obj.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid interval specified",
        )

    return start_date, end_date
