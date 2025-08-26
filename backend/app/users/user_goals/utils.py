from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from activities.activity.utils import ACTIVITY_ID_TO_NAME

import users.user_goals.schema as user_goals_schema
import users.user_goals.models as user_goals_models

import activities.activity.crud as activity_crud
import core.logger as core_logger


def calculate_goal_progress_by_activity_type(
    goal: user_goals_models.UserGoal,
    date: str,
    db: Session,
) -> user_goals_schema.UserGoalProgress:
    """
    Calculates the progress of a user's goal for a specific activity type within a given time interval.

    Args:
        goal (user_goals_models.UserGoal): The user goal object containing goal details.
        date (str): The reference date (in 'YYYY-MM-DD' format) to determine the interval for progress calculation.
        db (Session): The database session for querying user activities.

    Returns:
        user_goals_schema.UserGoalProgress: An object containing the progress metrics for the specified goal and activity type.

    Raises:
        HTTPException: If an error occurs during processing or database access.
    """
    try:
        start_date, end_date = get_start_end_date_by_interval(goal.interval, date)
        activities = activity_crud.get_user_activities_per_timeframe_and_activity_type(
            goal.user_id, goal.activity_type, start_date, end_date, db
        )

        if not activities:
            return user_goals_schema.UserGoalProgress(
                goal_id=goal.id,
                interval=goal.interval,
                activity_type=goal.activity_type,
                goal_type=goal.goal_type,
                activity_type_name=(
                    ACTIVITY_ID_TO_NAME[goal.activity_type]
                    if goal.activity_type
                    else None
                ),
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                goal_calories=goal.goal_calories,
                goal_count=goal.goal_activities_number,
                goal_distance=goal.goal_distance,
                goal_elevation=goal.goal_elevation,
                goal_duration=goal.goal_duration,
                goal_steps=goal.goal_steps,
            )

        total_duration = sum(
            activity.total_elapsed_time or 0 for activity in activities
        )
        total_distance = sum(activity.distance or 0 for activity in activities)
        total_elevation = sum(activity.elevation_gain or 0 for activity in activities)
        total_calories = sum(activity.calories or 0 for activity in activities)

        return user_goals_schema.UserGoalProgress(
            goal_id=goal.id,
            interval=goal.interval,
            activity_type=goal.activity_type,
            goal_type=goal.goal_type,
            activity_type_name=(
                ACTIVITY_ID_TO_NAME[goal.activity_type] if goal.activity_type else None
            ),
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            total_activities=len(activities),
            total_calories=total_calories,
            total_duration=total_duration,
            total_distance=total_distance,
            total_elevation=total_elevation,
            goal_calories=goal.goal_calories,
            goal_count=goal.goal_activities_number,
            goal_distance=goal.goal_distance,
            goal_elevation=goal.goal_elevation,
            goal_duration=goal.goal_duration,
            goal_steps=goal.goal_steps,
        )

    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in calculate_goal_progress_by_activity_type: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_start_end_date_by_interval(
    interval: str, date: str
) -> tuple[datetime, datetime]:
    """
    Calculates the start and end datetime objects for a given interval ('daily', 'weekly', or 'monthly') based on a provided date string.

    Args:
        interval (str): The interval type. Must be one of 'daily', 'weekly', or 'monthly'.
        date (str): The reference date in 'YYYY-MM-DD' format.

    Returns:
        tuple[datetime, datetime]: A tuple containing the start and end datetime objects for the specified interval.

    Raises:
        HTTPException: If the interval specified is not one of the accepted values.
    """
    date_obj = datetime.strptime(date, "%Y-%m-%d")

    if interval == "weekly":
        start_date = date_obj - timedelta(days=date_obj.weekday())  # Monday
        end_date = start_date + timedelta(
            days=6, hours=23, minutes=59, seconds=59
        )  # Sunday
    elif interval == "monthly":
        start_date = date_obj.replace(day=1)
        end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(
            seconds=1
        )  # Last day of the month
    elif interval == "daily":
        start_date = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = date_obj + timedelta(hours=23, minutes=59, seconds=59)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid interval specified"
        )

    return start_date, end_date
