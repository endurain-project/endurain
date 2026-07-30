"""
User goals module for managing user fitness goals.

This module provides CRUD operations and data models for user
goal tracking including activity type goals, intervals, and
progress calculation.

Exports:
    - CRUD: get_user_goals_by_user_id, get_user_goal_by_user_and_goal_id,
      create_user_goal, update_user_goal, delete_user_goal
    - Schemas: UsersGoalBase, UsersGoalCreate, UsersGoalUpdate,
      UsersGoalRead, UsersGoalProgress
    - Enums: Interval, ActivityType, GoalType
    - Utils: calculate_user_goals
"""

from .crud import (
    create_user_goal,
    delete_user_goal,
    get_user_goal_by_user_and_goal_id,
    get_user_goals_by_user_id,
    update_user_goal,
)
from .schema import (
    ActivityType,
    GoalType,
    Interval,
    UsersGoalBase,
    UsersGoalCreate,
    UsersGoalProgress,
    UsersGoalRead,
    UsersGoalUpdate,
)
from .utils import calculate_user_goals

__all__ = [
    "ActivityType",
    "GoalType",
    # Enums
    "Interval",
    # Pydantic schemas
    "UsersGoalBase",
    "UsersGoalCreate",
    "UsersGoalProgress",
    "UsersGoalRead",
    "UsersGoalUpdate",
    # Utility functions
    "calculate_user_goals",
    "create_user_goal",
    "delete_user_goal",
    "get_user_goal_by_user_and_goal_id",
    # CRUD operations
    "get_user_goals_by_user_id",
    "update_user_goal",
]
