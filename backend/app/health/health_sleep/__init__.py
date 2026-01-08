"""
Health sleep module for managing user sleep data.

This module provides CRUD operations and data models for user
sleep tracking including sleep duration, stages, quality metrics,
heart rate, SpO2, and sleep scoring.

Exports:
    - CRUD: get_health_sleep_number, get_all_health_sleep_by_user_id,
      get_health_sleep_by_id_and_user_id,
      get_health_sleep_with_pagination, get_health_sleep_by_date,
      create_health_sleep, edit_health_sleep, delete_health_sleep
    - Schemas: HealthSleepBase, HealthSleepCreate, HealthSleepUpdate,
      HealthSleepRead, HealthSleepListResponse, HealthSleepStage
    - Enums: Source, SleepStageType, HRVStatus, SleepScore
    - Models: HealthSleep (ORM model)
"""

from .crud import (
    get_health_sleep_number,
    get_all_health_sleep_by_user_id,
    get_health_sleep_by_id_and_user_id,
    get_health_sleep_with_pagination,
    get_health_sleep_by_date,
    create_health_sleep,
    edit_health_sleep,
    delete_health_sleep,
)
from .models import HealthSleep as HealthSleepModel
from .schema import (
    HealthSleepBase,
    HealthSleepCreate,
    HealthSleepUpdate,
    HealthSleepRead,
    HealthSleepListResponse,
    HealthSleepStage,
    Source,
    SleepStageType,
    HRVStatus,
    SleepScore,
)

__all__ = [
    # CRUD operations
    "get_health_sleep_number",
    "get_all_health_sleep_by_user_id",
    "get_health_sleep_by_id_and_user_id",
    "get_health_sleep_with_pagination",
    "get_health_sleep_by_date",
    "create_health_sleep",
    "edit_health_sleep",
    "delete_health_sleep",
    # Database model
    "HealthSleepModel",
    # Pydantic schemas
    "HealthSleepBase",
    "HealthSleepCreate",
    "HealthSleepUpdate",
    "HealthSleepRead",
    "HealthSleepListResponse",
    "HealthSleepStage",
    # Enums
    "Source",
    "SleepStageType",
    "HRVStatus",
    "SleepScore",
]
