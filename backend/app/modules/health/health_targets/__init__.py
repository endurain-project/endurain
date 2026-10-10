"""
Health targets module for managing user health goals.

This module provides CRUD operations and data models for user
health targets including weight, steps, and sleep goals.

Exports:
    - CRUD: get_health_targets_by_user_id, create_health_targets,
      edit_health_target
    - Schemas: HealthTargetsBase, HealthTargetsUpdate,
      HealthTargetsRead
"""

from .crud import (
    create_health_targets,
    edit_health_target,
    get_health_targets_by_user_id,
)
from .schema import (
    HealthTargetsBase,
    HealthTargetsRead,
    HealthTargetsUpdate,
)

__all__ = [
    "HealthTargetsBase",
    "HealthTargetsRead",
    "HealthTargetsUpdate",
    "create_health_targets",
    "edit_health_target",
    "get_health_targets_by_user_id",
]
