"""
FastAPI router for consolidated health endpoints.

This module provides endpoints that aggregate health data across
multiple health modules for efficient dashboard display.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import modules.auth.dependencies as auth_dependencies
import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_poop.crud as health_poop_crud
import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_water.crud as health_water_crud
import modules.health.health_weight.crud as health_weight_crud
import modules.health.schema as health_schema
import modules.users.users.utils as users_utils

# Define the API router
router = APIRouter()


@router.get(
    "/stats/daily",
    response_model=health_schema.HealthDashboardResponse,
    status_code=status.HTTP_200_OK,
)
def read_health_daily_stats(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_schema.HealthDashboardResponse:
    """
    Retrieve health daily stats and last weight record.

    Args:
        _check_scopes: Security dependency that validates the user has
            'health:read' scope.
        token_user_id: The ID of the authenticated user extracted from the
            access token.
        db: Database session for executing queries.

    Returns:
        HealthDashboardResponse: A consolidated response containing:
            - sleep: Latest sleep record with key metrics
            - weight: Latest weight and BMI data
            - steps: Today's step count
            - fasting: Active or most recent fasting session
            - water: Today's water intake in milliliters
            - poop: Today's bowel movement count

    Raises:
        HTTPException: If the user lacks required 'health:read' scope.
    """
    today = str(users_utils.user_local_today(token_user_id, db))

    # Get today's sleep
    today_sleep = health_sleep_crud.get_health_sleep_by_date_and_user_id(token_user_id, today, db)

    # Get latest weight (most recent record)
    latest_weight = health_weight_crud.get_latest_weight_by_user_id(token_user_id, db)

    # Get today's steps
    today_steps = health_steps_crud.get_health_steps_by_date_and_user_id(token_user_id, today, db)

    # Get active fasting or most recent
    active_fasting = health_fasting_crud.get_active_fasting_by_user_id(token_user_id, db)

    # Get today's water intake
    today_water = health_water_crud.get_health_water_by_date_and_user_id(token_user_id, today, db)

    # Get today's poop records
    today_poop_records = health_poop_crud.get_health_poop_by_date_and_user_id(token_user_id, today, db)

    # Build dashboard response with only necessary fields
    sleep_data = None
    if today_sleep and today_sleep.hrv_status is not None:
        sleep_data = health_schema.HealthSleepDashboard(
            total_sleep_seconds=today_sleep.total_sleep_seconds,
            resting_heart_rate=today_sleep.resting_heart_rate,
            hrv_status=str(today_sleep.hrv_status),
            avg_skin_temp_deviation=today_sleep.avg_skin_temp_deviation,
        )

    weight_data = None
    if latest_weight:
        weight_data = health_schema.HealthWeightDashboard(
            weight=latest_weight.weight,
            bmi=latest_weight.bmi,
        )

    steps_data = None
    if today_steps:
        steps_data = health_schema.HealthStepsDashboard(
            steps=today_steps.steps,
        )

    fasting_data = None
    if active_fasting and active_fasting.fast_start_time is not None and active_fasting.status is not None:
        fasting_data = health_schema.HealthFastingDashboard(
            id=active_fasting.id,
            fast_start_time=active_fasting.fast_start_time,
            fast_end_time=active_fasting.fast_end_time,
            status=str(active_fasting.status),
            actual_duration_seconds=active_fasting.actual_duration_seconds,
        )

    water_data = None
    if today_water and today_water.amount_ml is not None:
        water_data = health_schema.HealthWaterDashboard(
            amount_ml=float(today_water.amount_ml),
        )

    poop_data = None
    if today_poop_records:
        poop_data = health_schema.HealthPoopDashboard(
            count=len(today_poop_records),
        )

    return health_schema.HealthDashboardResponse(
        sleep=sleep_data,
        weight=weight_data,
        steps=steps_data,
        fasting=fasting_data,
        water=water_data,
        poop=poop_data,
    )
