"""
Health module aggregating all health-related sub-modules.

This module provides a unified interface for health tracking,
including sleep, weight, steps, fasting, water intake, bowel
movements, and health targets.

Sub-modules:
    - health_sleep: Sleep tracking and scoring
    - health_weight: Weight and body composition tracking
    - health_steps: Daily step count tracking
    - health_fasting: Fasting session tracking
    - health_water: Daily water intake tracking
    - health_poop: Bowel movement tracking
    - health_targets: User health goal targets

Top-level exports:
    - Constants: Interval
    - Utils: get_start_date_for_interval
    - Schemas: HealthListResponse, HealthDashboardResponse,
      HealthSleepDashboard, HealthWeightDashboard,
      HealthStepsDashboard, HealthFastingDashboard,
      HealthWaterDashboard, HealthPoopDashboard
"""

from .constants import Interval
from .schema import (
    HealthDashboardResponse,
    HealthFastingDashboard,
    HealthListResponse,
    HealthPoopDashboard,
    HealthSleepDashboard,
    HealthStepsDashboard,
    HealthWaterDashboard,
    HealthWeightDashboard,
)
from .utils import get_start_date_for_interval

__all__ = [
    "HealthDashboardResponse",
    "HealthFastingDashboard",
    # Shared schemas
    "HealthListResponse",
    "HealthPoopDashboard",
    "HealthSleepDashboard",
    "HealthStepsDashboard",
    "HealthWaterDashboard",
    "HealthWeightDashboard",
    # Constants
    "Interval",
    # Utilities
    "get_start_date_for_interval",
]
