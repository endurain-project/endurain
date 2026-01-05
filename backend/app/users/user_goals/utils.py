from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List

from activities.activity.utils import ACTIVITY_ID_TO_NAME

import users.user_goals.schema as user_goals_schema
import users.user_goals.models as user_goals_models
import users.user_goals.crud as user_goals_crud

import activities.activity.crud as activity_crud
import core.logger as core_logger


def calculate_user_goals(
    user_id: int, date: str | None, db: Session
) -> List[user_goals_schema.UserGoalProgress] | None:
    """
    Calculates the progress of all goals for a given user on a specified date.

    Args:
        user_id (int): The ID of the user whose goals are to be calculated.
        date (str | None): The date for which to calculate goal progress, in "YYYY-MM-DD" format. If None, uses the current date.
        db (Session): The SQLAlchemy database session.

    Returns:
        List[user_goals_schema.UserGoalProgress] | None:
            A list of UserGoalProgress objects representing the progress of each goal, or None if no goals are found.

    Raises:
        HTTPException: If an error occurs during calculation or database access.
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
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in calculate_user_goals: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def calculate_goal_progress_by_activity_type(
    goal: user_goals_models.UserGoal,
    date: str,
    db: Session,
) -> user_goals_schema.UserGoalProgress | None:
    """
    Calculates the progress of a user's goal for a specific activity type within a given time interval.
    This function determines the progress of a goal (calories, distance, elevation, duration, or number of activities)
    based on the user's activities of a specified type (run, bike, swim, walk) within the interval defined by the goal.
    It fetches relevant activities from the database, aggregates the required metrics, and computes the percentage
    completion of the goal.
    Args:
        goal (user_goals_models.UserGoal): The user goal object containing goal details and parameters.
        date (str): The reference date (in 'YYYY-MM-DD' format) to determine the interval for progress calculation.
        db (Session): The SQLAlchemy database session used for querying activities.
    Returns:
        user_goals_schema.UserGoalProgress | None: An object containing progress details for the goal, or None if no activities are found.
    Raises:
        HTTPException: If an error occurs during processing or database access.
    """
    try:
        start_date, end_date = get_start_end_date_by_interval(goal.interval, date)

        # Define activity type mappings
        TYPE_MAP = {
            user_goals_schema.ActivityType.RUN: [1, 2, 3, 34, 40],
            user_goals_schema.ActivityType.BIKE: [4, 5, 6, 7, 27, 28, 29, 35, 36],
            user_goals_schema.ActivityType.SWIM: [8, 9],
            user_goals_schema.ActivityType.WALK: [11, 12, 44],
            user_goals_schema.ActivityType.CARDIO: [20, 41, 46],
        }
        DEFAULT_TYPES = (10, 19)

        # Get activity types based on goal.activity_type, default to [10, 19]
        activity_types = TYPE_MAP.get(goal.activity_type, DEFAULT_TYPES)

        # Fetch all activities in a single query
        activities = activity_crud.get_user_activities_per_timeframe_and_activity_types(
            goal.user_id, activity_types, start_date, end_date, db, True
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
                percentage_completed = (total_calories / goal.goal_calories) * 100
            elif goal.goal_type == user_goals_schema.GoalType.DISTANCE:
                total_distance = sum(activity.distance or 0 for activity in activities)
                percentage_completed = (total_distance / goal.goal_distance) * 100
            elif goal.goal_type == user_goals_schema.GoalType.ELEVATION:
                total_elevation = sum(
                    activity.elevation_gain or 0 for activity in activities
                )
                percentage_completed = (total_elevation / goal.goal_elevation) * 100
            elif goal.goal_type == user_goals_schema.GoalType.DURATION:
                total_duration = sum(
                    activity.total_elapsed_time or 0 for activity in activities
                )
                percentage_completed = (total_duration / goal.goal_duration) * 100
            elif goal.goal_type == user_goals_schema.GoalType.ACTIVITIES:
                total_activities_number = len(activities)
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
    Return the start and end datetimes for the interval containing the given date.

    Parameters
    ----------
    interval : str
        One of "yearly", "monthly", "weekly", or "daily". Determines how the window is aligned:
        - "yearly": calendar year containing the date
        - "monthly": calendar month containing the date
        - "weekly": ISO week starting on Monday containing the date
        - "daily": the given calendar day
    date : str
        Date string in "YYYY-MM-DD" format. This is parsed with datetime.strptime(date, "%Y-%m-%d").

    Returns
    -------
    tuple[datetime, datetime]
        A pair (start_date, end_date) where:
        - start_date is the beginning of the requested interval (00:00:00 on the start day),
        - end_date is the last second of the requested interval (23:59:59 on the end day).
        Both datetimes are naive (no tzinfo) and use second precision.

    Raises
    ------
    HTTPException
        Raises an HTTPException with status_code=400 if an unsupported interval string is provided.

    Notes
    -----
    - "yearly": start is January 1st of the date's year at 00:00:00; end is the last second of December 31st.
    - "monthly": start is the first day of the month at 00:00:00; end is the last second of that month.
    - "weekly": start is the Monday of the week at 00:00:00; end is the following Sunday at 23:59:59.
    - "daily": start is the date at 00:00:00; end is the date at 23:59:59.
    - The implementation computes month/year boundaries by advancing to the next period and
      subtracting one second; if you need timezone-aware behavior or sub-second precision,
      convert inputs/outputs to timezone-aware datetimes and adjust the logic accordingly.

    Examples
    --------
    >>> get_start_end_date_by_interval("daily", "2023-03-15")
    (datetime(2023, 3, 15, 0, 0, 0), datetime(2023, 3, 15, 23, 59, 59))
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
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid interval specified"
        )

    return start_date, end_date
