"""
User goals module for managing user fitness goals.

This module provides CRUD operations and data models for user
goal tracking including activity type goals, intervals, and
progress calculation.

Exports:
    - CRUD: get_user_goals_by_user_id, get_user_goal_by_user_and_goal_id,
      create_user_goal, update_user_goal, delete_user_goal
    - Schemas: UserGoalBase, UserGoalCreate, UserGoalUpdate,
      UserGoalRead, UserGoalProgress
    - Models: UserGoal (ORM model)
    - Enums: Interval, ActivityType, GoalType
    - Utils: calculate_user_goals
"""

from .crud import (
    get_user_goals_by_user_id,
    get_user_goal_by_user_and_goal_id,
    create_user_goal,
    update_user_goal,
    delete_user_goal,
)
from .models import UserGoal as UserGoalModel
from .schema import (
    Interval,
    ActivityType,
    GoalType,
    UserGoalBase,
    UserGoalCreate,
    UserGoalUpdate,
    UserGoalRead,
    UserGoalProgress,
)
from .utils import calculate_user_goals

__all__ = [
    # CRUD operations
    "get_user_goals_by_user_id",
    "get_user_goal_by_user_and_goal_id",
    "create_user_goal",
    "update_user_goal",
    "delete_user_goal",
    # Database model
    "UserGoalModel",
    # Pydantic schemas
    "UserGoalBase",
    "UserGoalCreate",
    "UserGoalUpdate",
    "UserGoalRead",
    "UserGoalProgress",
    # Enums
    "Interval",
    "ActivityType",
    "GoalType",
    # Utility functions
    "calculate_user_goals",
]
