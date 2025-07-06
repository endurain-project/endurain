from typing import Annotated, Callable, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Security
from sqlalchemy.orm import Session

import users.user_goals.schema as user_goals_schema
import users.user_goals.crud as user_goals_crud

import session.security as session_security

import core.database as core_database

# Define the API router
router = APIRouter()

@router.post("", response_model=user_goals_schema.UserGoal)
async def create_user_goal(
    user_goal: user_goals_schema.UserGoalBase,
    db: Annotated[Session, Depends(core_database.get_db)],
    user_id: Annotated[int, Depends(session_security.get_user_id_from_access_token)],
):
    """Create a new user goal"""
    return user_goals_crud.create_user_goal(db=db, user_id=user_id, user_goal=user_goal)


@router.get("", response_model=List[user_goals_schema.UserGoal])
async def get_user_goals(
    db: Annotated[Session, Depends(core_database.get_db)],
    user_id: Annotated[int, Depends(session_security.get_user_id_from_access_token)],
):
    """Get all user goals for the current user"""
    return user_goals_crud.get_user_goals(db=db, user_id=user_id)


@router.put("", response_model=user_goals_schema.UserGoal)
async def update_user_goal(
    user_goal: user_goals_schema.UserGoalBase,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["user_goals:write"])
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    user_id: Annotated[int, Depends(session_security.get_user_id_from_access_token)],
):
    """Update a user goal"""
    return user_goals_crud.update_user_goal(db=db, user_id=user_id, goal_id=goal_id, user_goal=user_goal)


@router.delete("")
async def delete_user_goal(
    goal_id: int,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["user_goals:write"])
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    user_id: Annotated[int, Depends(session_security.get_user_id_from_access_token)],
):
    """Delete a user goal"""
    return user_goals_crud.delete_user_goal(db=db, user_id=user_id, goal_id=goal_id)

@router.get("/results", response_model=List[user_goals_schema.UserGoalProgress])
async def get_user_goals(
    db: Annotated[Session, Depends(core_database.get_db)],
    user_id: Annotated[int, Depends(session_security.get_user_id_from_access_token)],
    date: Optional[str] = datetime.now().strftime("%Y-%m-%d")
):
    """Get all user goals for the current user"""
    print(date)
    return user_goals_crud.calculate_user_goals(db=db, user_id=user_id, date=date)