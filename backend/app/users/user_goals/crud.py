from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

import users.user_goals.schema as user_goals_schema
import users.user_goals.models as user_goals_models
import users.user_goals.utils as user_goals_utils

import core.logger as core_logger


def get_user_goals_by_user_id(
    user_id: int, db: Session
) -> List[user_goals_models.UserGoal] | None:
    """
    Retrieve all goals associated with a specific user.
    Args:
        user_id (int): The ID of the user whose goals are to be retrieved.
        db (Session): The SQLAlchemy database session.
    Returns:
        List[user_goals_models.UserGoal] | None: A list of UserGoal objects if found, otherwise None.
    Raises:
        HTTPException: If an HTTP error occurs or an unexpected exception is raised.
    """
    try:
        goals = (
            db.query(user_goals_models.UserGoal)
            .filter(user_goals_models.UserGoal.user_id == user_id)
            .all()
        )

        if not goals:
            return None

        return goals
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_user_goals_by_user_id: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


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
        goals = get_user_goals_by_user_id(user_id, db)

        if not goals:
            return None

        return [
            user_goals_utils.calculate_goal_progress_by_activity_type(goal, date, db)
            for goal in goals
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


def create_user_goal(user_id: int, user_goal: user_goals_schema.UserGoalCreate, db: Session):
    """
    Creates a new user goal for a specific user, activity type, and interval.

    Checks if a goal with the same user, activity type, and interval already exists.
    If such a goal exists, raises an HTTP 409 Conflict error.
    Otherwise, creates and persists the new goal in the database.

    Args:
        user_id (int): The ID of the user for whom the goal is being created.
        user_goal (user_goals_schema.UserGoalCreate): The goal data to be created.
        db (Session): The SQLAlchemy database session.

    Returns:
        user_goals_models.UserGoalRead: The newly created user goal object.

    Raises:
        HTTPException: If a goal for the user, activity type, and interval already exists (409 Conflict),
                       or if an integrity/database error occurs (409 Conflict),
                       or for any other unexpected error (500 Internal Server Error).
    """
    try:
        existing_goals = (
            db.query(user_goals_models.UserGoal)
            .filter(user_goals_models.UserGoal.user_id == user_id)
            .filter(user_goals_models.UserGoal.interval == user_goal.interval)
            .filter(user_goals_models.UserGoal.activity_type == user_goal.activity_type)
            .filter(user_goals_models.UserGoal.goal_type == user_goal.goal_type)
            .all()
        )

        if existing_goals:
            # If there are existing goals for this user, interval, activity type, and goal type, raise an error
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already has a goal for this activity type, interval, and goal type.",
            )

        db_user_goal = user_goals_models.UserGoal(
            user_id=user_id,
            interval=user_goal.interval,
            activity_type=user_goal.activity_type,
            goal_type=user_goal.goal_type,
            goal_calories=user_goal.goal_calories,
            goal_activities_number=user_goal.goal_activities_number,
            goal_distance=user_goal.goal_distance,
            goal_elevation=user_goal.goal_elevation,
            goal_duration=user_goal.goal_duration,
        )
        db.add(db_user_goal)
        db.commit()
        db.refresh(db_user_goal)
        return db_user_goal
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in create_user_goal: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def update_user_goal(
    user_id: int, goal_id: int, user_goal: user_goals_schema.UserGoalRead, db: Session
):
    """
    Updates a user's goal in the database with the provided fields.

    Args:
        db (Session): SQLAlchemy database session.
        user_id (int): ID of the user whose goal is being updated.
        goal_id (int): ID of the goal to update.
        user_goal (user_goals_schema.UserGoalRead): Schema containing fields to update.

    Returns:
        user_goals_models.UserGoalRead: The updated user goal object.

    Raises:
        HTTPException: If the user goal is not found (404) or if an internal error occurs (500).
    """
    try:
        db_user_goal = (
            db.query(user_goals_models.UserGoal)
            .filter(
                user_goals_models.UserGoal.user_id == user_id,
                user_goals_models.UserGoal.id == goal_id,
            )
            .first()
        )

        if not db_user_goal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User goal not found"
            )

        # Update only provided fields
        update_data = user_goal.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_user_goal, field, value)

        db.commit()
        db.refresh(db_user_goal)
        return db_user_goal
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in update_user_goal: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_user_goal(user_id: int, goal_id: int, db: Session):
    """
    Delete a user's goal from the database and commit the change.
    Parameters:
        user_id (int): ID of the user who owns the goal to delete.
        goal_id (int): ID of the goal to delete.
        db (Session): SQLAlchemy Session used to perform the delete and commit.
    Returns:
        None
    Side effects:
        - Deletes the matching UserGoal record from the database.
        - Commits the transaction on success (db.commit()).
        - Logs unexpected exceptions via core_logger.print_to_log.
    Raises:
        HTTPException: 404 Not Found if no UserGoal matches the provided user_id and goal_id.
        HTTPException: 500 Internal Server Error for unexpected errors (these are logged before raising).
        HTTPException: Re-raises any HTTPException caught internally.
    Notes:
        - The deletion is performed using a filtered Query.delete() call; the change is only persisted
          after db.commit() succeeds.
        - This function does not perform an explicit db.rollback() on failure; callers that manage
          transactions should handle rollback as appropriate to avoid leaving the session in an inconsistent state.
    """
    try:
        # Delete the user goal
        num_deleted = (
            db.query(user_goals_models.UserGoal)
            .filter(
                user_goals_models.UserGoal.user_id == user_id,
                user_goals_models.UserGoal.id == goal_id,
            )
            .delete()
        )

        # Check if the user goal was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User goal not found"
            )
        
        # Commit the transaction
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in delete_user_goal: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
