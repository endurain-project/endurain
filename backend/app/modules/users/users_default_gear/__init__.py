"""
User default gear module for activity type gear assignments.

This module provides CRUD operations and data models for managing
user default gear settings per activity type (run, ride, swim, etc.).

Exports:
    - CRUD: get_user_default_gear_by_user_id,
      create_user_default_gear, edit_user_default_gear
    - Schemas: UsersDefaultGearBase, UsersDefaultGearUpdate,
      UsersDefaultGearRead
    - Utils: get_user_default_gear_by_activity_type
    - Constants: ACTIVITY_TYPE_TO_GEAR_ATTR
"""

from .crud import (
    create_user_default_gear,
    edit_user_default_gear,
    get_user_default_gear_by_user_id,
)
from .schema import (
    UsersDefaultGearBase,
    UsersDefaultGearRead,
    UsersDefaultGearUpdate,
)
from .utils import (
    ACTIVITY_TYPE_TO_GEAR_ATTR,
    get_user_default_gear_by_activity_type,
)

__all__ = [
    "ACTIVITY_TYPE_TO_GEAR_ATTR",
    "UsersDefaultGearBase",
    "UsersDefaultGearRead",
    "UsersDefaultGearUpdate",
    "create_user_default_gear",
    "edit_user_default_gear",
    "get_user_default_gear_by_activity_type",
    "get_user_default_gear_by_user_id",
]
