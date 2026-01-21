"""CRUD operations for user goals."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import users.users_goals.schema as user_goals_schema
import users.users_goals.models as user_goals_models

import core.decorators as core_decorators


@core_decorators.handle_db_errors
def get_user_goals_by_user_id(
    user_id: int,
    db: Session,
    interval: user_goals_schema.Interval | None = None,
    activity_type: user_goals_schema.ActivityType | None = None,
    goal_type: user_goals_schema.GoalType | None = None,
) -> list[user_goals_models.UsersGoal]:
    """
    Retrieve goals for a specific user with optional filters.

    Args:
        user_id: The ID of the user.
        db: SQLAlchemy database session.
        interval: Optional filter by goal interval.
        activity_type: Optional filter by activity type.
        goal_type: Optional filter by goal type.

    Returns:
        List of UsersGoal models matching the filters.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = select(user_goals_models.UsersGoal).where(
        user_goals_models.UsersGoal.user_id == user_id
    )

    if interval is not None:
        stmt = stmt.where(user_goals_models.UsersGoal.interval == interval.value)
    if activity_type is not None:
        stmt = stmt.where(
            user_goals_models.UsersGoal.activity_type == activity_type.value
        )
    if goal_type is not None:
        stmt = stmt.where(user_goals_models.UsersGoal.goal_type == goal_type.value)

    return db.execute(stmt).scalars().all()


@core_decorators.handle_db_errors
def get_user_goal_by_user_and_goal_id(
    user_id: int, goal_id: int, db: Session
) -> user_goals_models.UsersGoal | None:
    """
    Retrieve a specific goal by user ID and goal ID.

    Args:
        user_id: The ID of the user.
        goal_id: The ID of the goal.
        db: SQLAlchemy database session.

    Returns:
        UsersGoal model if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = select(user_goals_models.UsersGoal).where(
        user_goals_models.UsersGoal.user_id == user_id,
        user_goals_models.UsersGoal.id == goal_id,
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def create_user_goal(
    user_id: int,
    user_goal: user_goals_schema.UsersGoalCreate,
    db: Session,
) -> user_goals_models.UsersGoal:
    """
    Create a new user goal.

    Args:
        user_id: The ID of the user.
        user_goal: Goal data to create.
        db: SQLAlchemy database session.

    Returns:
        The created UsersGoal model.

    Raises:
        HTTPException: If goal already exists (409) or database
            error occurs (500).
    """
    try:
        # Check if goal already exists
        stmt = select(user_goals_models.UsersGoal).where(
            user_goals_models.UsersGoal.user_id == user_id,
            user_goals_models.UsersGoal.interval == user_goal.interval,
            user_goals_models.UsersGoal.activity_type == user_goal.activity_type,
            user_goals_models.UsersGoal.goal_type == user_goal.goal_type,
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

        db_user_goal = user_goals_models.UsersGoal(
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
    except HTTPException:
        raise


@core_decorators.handle_db_errors
def update_user_goal(
    user_id: int,
    user_goal: user_goals_schema.UsersGoalUpdate,
    db: Session,
) -> user_goals_models.UsersGoal:
    """
    Update a user's goal.

    Args:
        user_id: ID of the user.
        user_goal: Schema with fields to update.
        db: SQLAlchemy database session.

    Returns:
        The updated UsersGoal model.

    Raises:
        HTTPException: If goal not found (404) or database
            error occurs (500).
    """
    if user_goal.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit user goal for another user",
        )

    db_user_goal = get_user_goal_by_user_and_goal_id(user_id, user_goal.id, db)

    if not db_user_goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User goal not found",
        )

    # Update only provided fields
    update_data = user_goal.model_dump(exclude_unset=True, exclude={"user_id", "id"})
    for field, value in update_data.items():
        setattr(db_user_goal, field, value)

    db.commit()
    db.refresh(db_user_goal)
    return db_user_goal


@core_decorators.handle_db_errors
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
    db_user_goal = get_user_goal_by_user_and_goal_id(user_id, goal_id, db)

    if not db_user_goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User goal not found",
        )

    db.delete(db_user_goal)
    db.commit()
