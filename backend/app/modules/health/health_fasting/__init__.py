"""
Health fasting module for managing user fasting session data.

This module provides CRUD operations and data models for user
fasting tracking including session timing, duration, fasting type,
status, and optional notes.

Exports:
    - CRUD: get_health_fasting_number_by_user_id,
      get_health_fasting_by_id_and_user_id,
      get_health_fasting_by_user_id,
      get_active_fasting_by_user_id,
      get_completed_fasting_count,
      get_total_fasting_seconds,
      get_avg_fasting_duration,
      get_completed_fasting_dates_by_user_id,
      create_health_fasting, edit_health_fasting,
      complete_health_fasting, delete_health_fasting
    - Schemas: HealthFastingBase, HealthFastingCreate,
      HealthFastingUpdate, HealthFastingRead,
      HealthFastingComplete, HealthFastingListResponse,
      HealthFastingStatsResponse
    - Enums: Source, FastingType, FastingStatus
"""

from .crud import (
    complete_health_fasting,
    create_health_fasting,
    delete_health_fasting,
    edit_health_fasting,
    get_active_fasting_by_user_id,
    get_avg_fasting_duration,
    get_completed_fasting_count,
    get_completed_fasting_dates_by_user_id,
    get_health_fasting_by_id_and_user_id,
    get_health_fasting_by_user_id,
    get_health_fasting_number_by_user_id,
    get_total_fasting_seconds,
)
from .schema import (
    FastingStatus,
    FastingType,
    HealthFastingBase,
    HealthFastingComplete,
    HealthFastingCreate,
    HealthFastingListResponse,
    HealthFastingRead,
    HealthFastingStatsResponse,
    HealthFastingUpdate,
    Source,
)

__all__ = [
    "FastingStatus",
    "FastingType",
    "HealthFastingBase",
    "HealthFastingComplete",
    "HealthFastingCreate",
    "HealthFastingListResponse",
    "HealthFastingRead",
    "HealthFastingStatsResponse",
    "HealthFastingUpdate",
    "Source",
    "complete_health_fasting",
    "create_health_fasting",
    "delete_health_fasting",
    "edit_health_fasting",
    "get_active_fasting_by_user_id",
    "get_avg_fasting_duration",
    "get_completed_fasting_count",
    "get_completed_fasting_dates_by_user_id",
    "get_health_fasting_by_id_and_user_id",
    "get_health_fasting_by_user_id",
    "get_health_fasting_number_by_user_id",
    "get_total_fasting_seconds",
]
