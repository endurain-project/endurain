"""
Health weight module for managing user weight and body composition.

This module provides CRUD operations and data models for user
weight tracking including BMI, body composition metrics, and
various health indicators.

Exports:
    - CRUD: get_all_health_weight, get_health_weight_number_by_user_id,
      get_all_health_weight_by_user_id,
      get_health_weight_by_user_id, get_health_weight_by_date_and_user_id,
      create_health_weight, edit_health_weight, delete_health_weight
    - Schemas: HealthWeightBase, HealthWeightCreate,
      HealthWeightUpdate, HealthWeightRead,
      HealthWeightListResponse
    - Enums: Source
    - Utils: calculate_bmi, calculate_bmi_all_user_entries
"""

from .crud import (
    create_health_weight,
    delete_health_weight,
    edit_health_weight,
    get_all_health_weight,
    get_all_health_weight_by_user_id,
    get_health_weight_by_date_and_user_id,
    get_health_weight_by_user_id,
    get_health_weight_number_by_user_id,
)
from .schema import (
    HealthWeightBase,
    HealthWeightCreate,
    HealthWeightListResponse,
    HealthWeightRead,
    HealthWeightUpdate,
    Source,
)
from .utils import calculate_bmi, calculate_bmi_all_user_entries

__all__ = [
    "HealthWeightBase",
    "HealthWeightCreate",
    "HealthWeightListResponse",
    "HealthWeightRead",
    "HealthWeightUpdate",
    "Source",
    "calculate_bmi",
    "calculate_bmi_all_user_entries",
    "create_health_weight",
    "delete_health_weight",
    "edit_health_weight",
    "get_all_health_weight",
    "get_all_health_weight_by_user_id",
    "get_health_weight_by_date_and_user_id",
    "get_health_weight_by_user_id",
    "get_health_weight_number_by_user_id",
]
