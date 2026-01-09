"""
Health weight module for managing user weight and body composition.

This module provides CRUD operations and data models for user
weight tracking including BMI, body composition metrics, and
various health indicators.

Exports:
    - CRUD: get_all_health_weight, get_health_weight_number,
      get_all_health_weight_by_user_id,
      get_health_weight_by_id_and_user_id,
      get_health_weight_with_pagination, get_health_weight_by_date,
      create_health_weight, edit_health_weight, delete_health_weight
    - Schemas: HealthWeightBase, HealthWeightCreate,
      HealthWeightUpdate, HealthWeightRead,
      HealthWeightListResponse
    - Enums: Source
    - Models: HealthWeight (ORM model)
    - Utils: calculate_bmi, calculate_bmi_all_user_entries
"""

from .crud import (
    get_all_health_weight,
    get_health_weight_number,
    get_all_health_weight_by_user_id,
    get_health_weight_by_id_and_user_id,
    get_health_weight_with_pagination,
    get_health_weight_by_date,
    create_health_weight,
    edit_health_weight,
    delete_health_weight,
)
from .models import HealthWeight as HealthWeightModel
from .schema import (
    HealthWeightBase,
    HealthWeightCreate,
    HealthWeightUpdate,
    HealthWeightRead,
    HealthWeightListResponse,
    Source,
)
from .utils import calculate_bmi, calculate_bmi_all_user_entries

__all__ = [
    # CRUD operations
    "get_all_health_weight",
    "get_health_weight_number",
    "get_all_health_weight_by_user_id",
    "get_health_weight_by_id_and_user_id",
    "get_health_weight_with_pagination",
    "get_health_weight_by_date",
    "create_health_weight",
    "edit_health_weight",
    "delete_health_weight",
    # Database model
    "HealthWeightModel",
    # Pydantic schemas
    "HealthWeightBase",
    "HealthWeightCreate",
    "HealthWeightUpdate",
    "HealthWeightRead",
    "HealthWeightListResponse",
    # Enums
    "Source",
    # Utilities
    "calculate_bmi",
    "calculate_bmi_all_user_entries",
]
