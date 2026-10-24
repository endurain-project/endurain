"""FastAPI router for health water intake endpoints.

This module defines the API endpoints for managing water intake
records, including CRUD operations with pagination and filtering.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    Security,
    status,
)

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_water.schema as health_water_schema
import modules.health.health_water.service as health_water_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=(health_water_schema.HealthWaterListResponse),
    status_code=status.HTTP_200_OK,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:read"],
        )
    ],
)
def read_health_water_all_pagination(
    _validate_pagination_values_on_query: Annotated[
        Callable,
        Depends(core_dependencies.validate_pagination_values_on_query),
    ],
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page_number: Annotated[
        int | None,
        Query(description="Pagination page number"),
    ] = None,
    num_records: Annotated[
        int | None,
        Query(description="Number of records per page"),
    ] = None,
    interval: Annotated[
        health_constants.Interval | None,
        Query(description="Filter by goal interval"),
    ] = None,
) -> health_water_schema.HealthWaterListResponse:
    """Retrieve paginated water intake records for the user.

    Args:
        _validate_pagination_values_on_query: Dependency that
            validates pagination parameters.
        token_user_id: The ID of the authenticated user
            extracted from the access token.
        db: Database session for executing queries.
        page_number: Optional pagination page number.
        num_records: Optional number of records per page.
        interval: Optional filter by goal interval.

    Returns:
        HealthWaterListResponse containing total count,
            pagination info, and water intake records.

    Raises:
        HTTPException: If the user lacks required scope or
            pagination values are invalid.
    """
    return health_water_service.list_health_water(token_user_id, db, page_number, num_records, interval)


@router.post(
    "",
    response_model=health_water_schema.HealthWaterRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:write"],
        )
    ],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_health_water(
    request: Request,
    health_water: health_water_schema.HealthWaterCreate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_water_schema.HealthWaterRead:
    """Create or update a water intake record for the user.

    If a record already exists for the given date, it will be
    updated instead of creating a duplicate.

    Args:
        request: The incoming request, read by the rate limiter.
        health_water: Water intake data to create.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Created or updated HealthWaterRead record.

    """
    return health_water_service.create_health_water(token_user_id, health_water, db)


@router.put(
    "",
    response_model=health_water_schema.HealthWaterRead,
    status_code=status.HTTP_200_OK,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:write"],
        )
    ],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_health_water(
    request: Request,
    health_water: health_water_schema.HealthWaterUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_water_schema.HealthWaterRead:
    """Edit an existing water intake record.

    Args:
        request: The incoming request, read by the rate limiter.
        health_water: Water intake data to update.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Updated HealthWaterRead record.

    Raises:
        HTTPException: If record not found or unauthorized.
    """
    return health_water_service.edit_health_water(token_user_id, health_water, db)


@router.delete(
    "/{health_water_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:write"],
        )
    ],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_health_water(
    request: Request,
    health_water_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Delete a water intake record for the authenticated user.

    Args:
        request: The incoming request, read by the rate limiter.
        health_water_id: ID of the water intake record.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Raises:
        HTTPException: If record not found or unauthorized.
    """
    health_water_service.delete_health_water(token_user_id, health_water_id, db)
