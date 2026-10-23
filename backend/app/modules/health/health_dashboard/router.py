"""FastAPI router for the consolidated daily health dashboard."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import modules.auth.dependencies as auth_dependencies
import modules.health.health_dashboard.schema as health_dashboard_schema
import modules.health.health_dashboard.service as health_dashboard_service

router = APIRouter()


@router.get(
    "/stats/daily",
    response_model=health_dashboard_schema.HealthDashboardResponse,
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
) -> health_dashboard_schema.HealthDashboardResponse:
    """Retrieve the user's health dashboard for today.

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
    return health_dashboard_service.get_daily_stats(token_user_id, db)
