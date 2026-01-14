"""CRUD operations for user goals."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

import users.user_goals.schema as user_goals_schema
import users.user_goals.models as user_goals_models

import core.logger as core_logger


def get_user_goals_by_user_id(
    user_id: int,
    db: Session,
    interval: user_goals_schema.Interval | None = None,
    activity_type: user_goals_schema.ActivityType | None = None,
    goal_type: user_goals_schema.GoalType | None = None,
) -> list[user_goals_models.UserGoal]:
    """
    Retrieve goals for a specific user with optional filters.

    Args:
        user_id: The ID of the user.
        db: SQLAlchemy database session.
        interval: Optional filter by goal interval.
        activity_type: Optional filter by activity type.
        goal_type: Optional filter by goal type.

    Returns:
        List of UserGoal models matching the filters.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        stmt = select(user_goals_models.UserGoal).where(
            user_goals_models.UserGoal.user_id == user_id
        )

        if interval is not None:
            stmt = stmt.where(user_goals_models.UserGoal.interval == interval.value)
        if activity_type is not None:
            stmt = stmt.where(
                user_goals_models.UserGoal.activity_type == activity_type.value
            )
        if goal_type is not None:
            stmt = stmt.where(user_goals_models.UserGoal.goal_type == goal_type.value)

        return db.execute(stmt).scalars().all()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_user_goals_by_user_id: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_user_goal_by_user_and_goal_id(
    user_id: int, goal_id: int, db: Session
) -> user_goals_models.UserGoal | None:
    """
    Retrieve a specific goal by user ID and goal ID.

    Args:
        user_id: The ID of the user.
        goal_id: The ID of the goal.
        db: SQLAlchemy database session.

    Returns:
        UserGoal model if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        stmt = select(user_goals_models.UserGoal).where(
            user_goals_models.UserGoal.user_id == user_id,
            user_goals_models.UserGoal.id == goal_id,
        )
        return db.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_user_goal_by_user_and_goal_id: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def create_user_goal(
    user_id: int,
    user_goal: user_goals_schema.UserGoalCreate,
    db: Session,
) -> user_goals_models.UserGoal:
    """
    Create a new user goal.

    Args:
        user_id: The ID of the user.
        user_goal: Goal data to create.
        db: SQLAlchemy database session.

    Returns:
        The created UserGoal model.

    Raises:
        HTTPException: If goal already exists (409) or database
            error occurs (500).
    """
    try:
        # Check if goal already exists
        stmt = select(user_goals_models.UserGoal).where(
            user_goals_models.UserGoal.user_id == user_id,
            user_goals_models.UserGoal.interval == user_goal.interval,
            user_goals_models.UserGoal.activity_type == user_goal.activity_type,
            user_goals_models.UserGoal.goal_type == user_goal.goal_type,
        )
        existing_goal = db.execute(stmt).scalar_one_or_none()

        if existing_goal:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "User already has a goal for this activity type, "
                    "interval, and goal type."
                ),
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
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in create_user_goal: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def update_user_goal(
    user_id: int,
    goal_id: int,
    user_goal: user_goals_schema.UserGoalEdit,
    db: Session,
) -> user_goals_models.UserGoal:
    """
    Update a user's goal.

    Args:
        user_id: ID of the user.
        goal_id: ID of the goal to update.
        user_goal: Schema with fields to update.
        db: SQLAlchemy database session.

    Returns:
        The updated UserGoal model.

    Raises:
        HTTPException: If goal not found (404) or database
            error occurs (500).
    """
    try:
        db_user_goal = get_user_goal_by_user_and_goal_id(user_id, goal_id, db)

        if not db_user_goal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User goal not found",
            )

        if user_id != db_user_goal.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot edit user goal for another user",
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
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in update_user_goal: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def delete_user_goal(user_id: int, goal_id: int, db: Session) -> None:
    """
    Delete a user's goal from the database.

    Args:
        user_id: ID of the user who owns the goal.
        goal_id: ID of the goal to delete.
        db: SQLAlchemy database session.

    Raises:
        HTTPException: If goal not found (404) or database
            error occurs (500).
    """
    try:
        db_user_goal = get_user_goal_by_user_and_goal_id(user_id, goal_id, db)

        if not db_user_goal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User goal not found",
            )

        db.delete(db_user_goal)
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in delete_user_goal: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err
