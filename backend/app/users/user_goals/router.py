from typing import Annotated, List, Callable
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import users.user_goals.dependencies as user_goals_dependencies
import users.user_goals.schema as user_goals_schema
import users.user_goals.crud as user_goals_crud
import users.user_goals.utils as user_goals_utils

import auth.security as auth_security

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get("", response_model=List[user_goals_schema.UserGoalRead] | None)
async def get_user_goals(
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """
    Retrieve the goals associated with the authenticated user.

    Args:
        token_user_id (int): The ID of the user extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        List[UserGoalRead]: A list of user goal objects for the authenticated user.
    """
    return user_goals_crud.get_user_goals_by_user_id(token_user_id, db)


@router.get("/results", response_model=List[user_goals_schema.UserGoalProgress] | None)
async def get_user_goals_results(
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """
    Retrieve the results of user goals.

    Args:
        token_user_id (int): The ID of the user extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        Any: The calculated user goals results for the specified user.
    """
    return user_goals_utils.calculate_user_goals(token_user_id, None, db)


@router.post("", response_model=user_goals_schema.UserGoalRead, status_code=201)
async def create_user_goal(
    user_goal: user_goals_schema.UserGoalCreate,
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """
    Creates a new user goal for the authenticated user.

    Args:
        user_goal (user_goals_schema.UserGoalCreate): The data for the new user goal.
        token_user_id (int): The ID of the user extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        The created user goal object.

    Raises:
        Depends on the implementation of user_goals_crud.create_user_goal.
    """
    return user_goals_crud.create_user_goal(token_user_id, user_goal, db)


@router.put("/{goal_id}", response_model=user_goals_schema.UserGoalRead)
async def update_user_goal(
    goal_id: int,
    validate_id: Annotated[Callable, Depends(user_goals_dependencies.validate_goal_id)],
    user_goal: user_goals_schema.UserGoalEdit,
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """
    Update a user's goal with new data.

    Args:
        goal_id (int): The ID of the goal to update.
        validate_id (Callable): Dependency that validates the goal ID.
        user_goal (user_goals_schema.UserGoalEdit): The updated goal data.
        token_user_id (int): The user ID extracted from the access token.
        db (Session): Database session dependency.

    Returns:
        The updated user goal object.

    Raises:
        HTTPException: If the goal ID is invalid or the update fails.
    """
    return user_goals_crud.update_user_goal(token_user_id, goal_id, user_goal, db)


@router.delete("/{goal_id}")
async def delete_user_goal(
    goal_id: int,
    validate_id: Annotated[Callable, Depends(user_goals_dependencies.validate_goal_id)],
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """
    Deletes a user goal from the database.

    Args:
        goal_id (int): The ID of the goal to be deleted.
        validate_id (Callable): Dependency that validates the goal ID.
        token_user_id (int): The ID of the user extracted from the access token.
        db (Session): Database session dependency.

    Returns:
        Any: The result of the delete operation from user_goals_crud.
    """
    return user_goals_crud.delete_user_goal(token_user_id, goal_id, db)
