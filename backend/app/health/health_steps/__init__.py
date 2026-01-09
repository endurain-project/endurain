"""
Health steps module for managing user step count data.

This module provides CRUD operations and data models for user
step tracking including daily step counts and data sources.

Exports:
    - CRUD: get_health_steps_number, get_all_health_steps_by_user_id,
      get_health_steps_by_id_and_user_id,
      get_health_steps_with_pagination, get_health_steps_by_date,
      create_health_steps, edit_health_steps, delete_health_steps
    - Schemas: HealthStepsBase, HealthStepsCreate, HealthStepsUpdate,
      HealthStepsRead, HealthStepsListResponse
    - Enums: Source
    - Models: HealthSteps (ORM model)
"""

from .crud import (
    get_health_steps_number,
    get_all_health_steps_by_user_id,
    get_health_steps_by_id_and_user_id,
    get_health_steps_with_pagination,
    get_health_steps_by_date,
    create_health_steps,
    edit_health_steps,
    delete_health_steps,
)
from .models import HealthSteps as HealthStepsModel
from .schema import (
    HealthStepsBase,
    HealthStepsCreate,
    HealthStepsUpdate,
    HealthStepsRead,
    HealthStepsListResponse,
    Source,
)

__all__ = [
    # CRUD operations
    "get_health_steps_number",
    "get_all_health_steps_by_user_id",
    "get_health_steps_by_id_and_user_id",
    "get_health_steps_with_pagination",
    "get_health_steps_by_date",
    "create_health_steps",
    "edit_health_steps",
    "delete_health_steps",
    # Database model
    "HealthStepsModel",
    # Pydantic schemas
    "HealthStepsBase",
    "HealthStepsCreate",
    "HealthStepsUpdate",
    "HealthStepsRead",
    "HealthStepsListResponse",
    # Enums
    "Source",
]
