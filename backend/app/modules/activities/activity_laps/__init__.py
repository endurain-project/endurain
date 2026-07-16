"""
Activity laps sub-module for per-lap metrics within an activity.

This module provides CRUD operations, schemas, ORM models, and routes
for activity laps imported from fitness files (.fit, .tcx, .gpx) or
third-party providers, including per-lap distance, duration, heart
rate, power, cadence, and altitude metrics.

Exports:
    - CRUD: get_activity_laps, get_activities_laps,
      get_public_activity_laps, create_activity_laps
    - Schemas: ActivityLapsBase, ActivityLapsRead
    - Models: ActivityLaps (ORM model)
    - Routers: router (authenticated), public_router
"""

from .crud import (
    create_activity_laps,
    get_activities_laps,
    get_activity_laps,
    get_public_activity_laps,
)
from .models import ActivityLaps
from .schema import ActivityLapsBase, ActivityLapsRead

__all__ = [
    # ORM models
    "ActivityLaps",
    # Pydantic schemas
    "ActivityLapsBase",
    "ActivityLapsRead",
    # CRUD operations
    "create_activity_laps",
    "get_activities_laps",
    "get_activity_laps",
    "get_public_activity_laps",
]
