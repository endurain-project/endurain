"""FastAPI router for the consolidated daily health dashboard."""

from fastapi import APIRouter, Security, status

import core.dependencies as core_dependencies
import modules.auth.dependencies as auth_dependencies
import modules.health.health_dashboard.schema as health_dashboard_schema
import modules.health.health_dashboard.service as health_dashboard_service

router = APIRouter()


@router.get(
    "/stats/daily",
    response_model=health_dashboard_schema.HealthDashboardResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_daily_stats(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_dashboard_schema.HealthDashboardResponse:
    """Retrieve the user's health dashboard for today.

    Args:
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
