"""FastAPI router for the consolidated daily health dashboard."""

from fastapi import APIRouter, Request, Security

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.health_dashboard.schema as health_dashboard_schema
import modules.health.health_dashboard.service as health_dashboard_service

router = APIRouter()


@router.get(
    "/stats/daily",
    response_model=health_dashboard_schema.HealthDashboardResponse,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.EXPENSIVE_READ)
def read_health_daily_stats(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_dashboard_schema.HealthDashboardResponse:
    """Retrieve the user's health dashboard for today.

    Args:
        request: The incoming request, read by the rate limiter.
        token_user_id: The ID of the authenticated user extracted from the
            access token.
        db: Database session for executing queries.

    Returns:
        The consolidated daily metrics and the user's health targets.
    """
    return health_dashboard_service.get_daily_stats(token_user_id, db)
