"""
User default gear module for activity type gear assignments.

This module provides CRUD operations and data models for managing
user default gear settings per activity type (run, ride, swim, etc.).

Exports:
    - CRUD: get_user_default_gear_by_user_id,
      create_user_default_gear, edit_user_default_gear
    - Schemas: UsersDefaultGearBase, UsersDefaultGearUpdate,
      UsersDefaultGearRead
    - Models: UsersDefaultGear (ORM model)
    - Utils: get_user_default_gear_by_activity_type
    - Constants: ACTIVITY_TYPE_TO_GEAR_ATTR
"""

from .crud import (
    get_user_default_gear_by_user_id,
    create_user_default_gear,
    edit_user_default_gear,
)
from .models import UsersDefaultGear as UsersDefaultGearModel
from .schema import (
    UsersDefaultGearBase,
    UsersDefaultGearUpdate,
    UsersDefaultGearRead,
)
from .utils import (
    get_user_default_gear_by_activity_type,
    ACTIVITY_TYPE_TO_GEAR_ATTR,
)

__all__ = [
    # CRUD operations
    "get_user_default_gear_by_user_id",
    "create_user_default_gear",
    "edit_user_default_gear",
    # Database model
    "UsersDefaultGearModel",
    # Pydantic schemas
    "UsersDefaultGearBase",
    "UsersDefaultGearUpdate",
    "UsersDefaultGearRead",
    # Utility functions
    "get_user_default_gear_by_activity_type",
    # Constants
    "ACTIVITY_TYPE_TO_GEAR_ATTR",
]
