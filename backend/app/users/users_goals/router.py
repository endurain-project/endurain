"""User goals API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

import users.users_goals.dependencies as user_goals_dependencies
import users.users_goals.schema as user_goals_schema
import users.users_goals.crud as user_goals_crud
import users.users_goals.utils as user_goals_utils

import auth.security as auth_security

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=list[user_goals_schema.UsersGoalRead],
    status_code=status.HTTP_200_OK,
)
async def get_user_goals(
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    interval: Annotated[
        user_goals_schema.Interval | None,
        Query(description="Filter by goal interval"),
    ] = None,
    activity_type: Annotated[
        user_goals_schema.ActivityType | None,
        Query(description="Filter by activity type"),
    ] = None,
    goal_type: Annotated[
        user_goals_schema.GoalType | None,
        Query(description="Filter by goal type"),
    ] = None,
) -> list[user_goals_schema.UsersGoalRead]:
    """
    Retrieve goals for the authenticated user with optional filters.

    Args:
        token_user_id: User ID from access token.
        db: Database session dependency.
        interval: Optional filter by goal interval.
        activity_type: Optional filter by activity type.
        goal_type: Optional filter by goal type.

    Returns:
        List of user goal objects matching the filters.
    """
    # Pydantic will convert ORM models to HealthWeightRead via from_attributes=True
    return user_goals_crud.get_user_goals_by_user_id(
        user_id=token_user_id,
        db=db,
        interval=interval,
        activity_type=activity_type,
        goal_type=goal_type,
    )  # type: ignore[arg-type]


@router.get(
    "/results",
    response_model=list[user_goals_schema.UsersGoalProgress] | None,
    status_code=status.HTTP_200_OK,
)
async def get_user_goals_results(
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[user_goals_schema.UsersGoalProgress] | None:
    """
    Calculate and retrieve goal progress for authenticated user.

    Args:
        token_user_id: User ID from access token.
        db: Database session dependency.

    Returns:
        List of goal progress objects, or None if no goals.
    """
    return user_goals_utils.calculate_user_goals(token_user_id, None, db)


@router.post(
    "",
    response_model=user_goals_schema.UsersGoalRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_goal(
    user_goal: user_goals_schema.UsersGoalCreate,
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> user_goals_schema.UsersGoalRead:
    """
    Create a new goal for the authenticated user.

    Args:
        user_goal: Goal data to create.
        token_user_id: User ID from access token.
        db: Database session dependency.

    Returns:
        The created goal object.
    """
    return user_goals_crud.create_user_goal(token_user_id, user_goal, db)


@router.put(
    "",
    status_code=status.HTTP_200_OK,
    response_model=user_goals_schema.UsersGoalRead,
)
async def update_user_goal(
    user_goal: user_goals_schema.UsersGoalUpdate,
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> user_goals_schema.UsersGoalRead:
    """
    Update an existing goal for the authenticated user.

    Args:
        user_goal: Updated goal data.
        token_user_id: User ID from access token.
        db: Database session dependency.

    Returns:
        The updated goal object.
    """
    return user_goals_crud.update_user_goal(token_user_id, user_goal, db)


@router.delete(
    "/{goal_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_user_goal(
    goal_id: int,
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    _: None = Depends(user_goals_dependencies.validate_goal_id),
) -> None:
    """
    Delete a goal for the authenticated user.

    Args:
        goal_id: ID of the goal to delete.
        token_user_id: User ID from access token.
        db: Database session dependency.
    """
    return user_goals_crud.delete_user_goal(token_user_id, goal_id, db)
