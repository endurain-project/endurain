"""
Health targets module for managing user health goals.

This module provides CRUD operations and data models for user
health targets including weight, steps, and sleep goals.

Exports:
    - CRUD: get_health_targets_by_user_id, create_health_targets,
      edit_health_target
    - Schemas: HealthTargetsBase, HealthTargetsUpdate,
      HealthTargetsRead
    - Models: HealthTargets (ORM model)
"""

from .crud import (
    get_health_targets_by_user_id,
    create_health_targets,
    edit_health_target,
)
from .models import HealthTargets as HealthTargetsModel
from .schema import (
    HealthTargetsBase,
    HealthTargetsRead,
    HealthTargetsUpdate,
)

__all__ = [
    # CRUD operations
    "get_health_targets_by_user_id",
    "create_health_targets",
    "edit_health_target",
    # Database model
    "HealthTargetsModel",
    # Pydantic schemas
    "HealthTargetsBase",
    "HealthTargetsRead",
    "HealthTargetsUpdate",
]
