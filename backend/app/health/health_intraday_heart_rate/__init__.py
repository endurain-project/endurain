"""
Health intraday heart rate module for managing user intraday heart rate data.

This module provides CRUD operations and data models for user
heart rate measurements and data sources.

Exports:
    - CRUD: get_all_health_intraday_heart_rate_by_user_id,
      get_health_intraday_heart_rate_by_id_and_user_id,
      get_health_intraday_heart_rate_with_pagination, get_health_intraday_heart_rate_by_timerange,
      create_health_intraday_heart_rate, edit_health_intraday_heart_rate, delete_health_intraday_heart_rate
    - Schemas: HealthIntradayHeartrateBase, HealthIntradayHeartrateCreate, HealthIntradayHeartrateUpdate,
      HealthIntradayHeartrateRead, HealthIntradayHeartrateListResponse
    - Enums: Source
    - Models: HealthIntradayHeartrate (ORM model)
"""

from .crud import (
    get_all_health_intraday_heart_rate_by_user_id,
    get_health_intraday_heart_rate_by_id_and_user_id,
    get_health_intraday_heart_rate_with_pagination,
    get_health_intraday_heart_rate_by_timerange,
    create_health_intraday_heart_rate,
    edit_health_intraday_heart_rate,
    delete_health_intraday_heart_rate,
)
from .models import HealthIntradayHeartrate as HealthIntradayHeartrateModel
from .schema import (
    HealthIntradayHeartrateBase,
    HealthIntradayHeartrateCreate,
    HealthIntradayHeartrateUpdate,
    HealthIntradayHeartrateRead,
    HealthIntradayHeartrateListResponse,
    Source,
)

__all__ = [
    # CRUD operations
    "get_all_health_intraday_heart_rate_by_user_id",
    "get_health_intraday_heart_rate_by_id_and_user_id",
    "get_health_intraday_heart_rate_with_pagination",
    "get_health_intraday_heart_rate_by_timerange",
    "create_health_intraday_heart_rate",
    "edit_health_intraday_heart_rate",
    "delete_health_intraday_heart_rate",
    # Database model
    "HealthIntradayHeartrateModel",
    # Pydantic schemas
    "HealthIntradayHeartrateBase",
    "HealthIntradayHeartrateCreate",
    "HealthIntradayHeartrateUpdate",
    "HealthIntradayHeartrateRead",
    "HealthIntradayHeartrateListResponse",
    # Enums
    "Source",
]
