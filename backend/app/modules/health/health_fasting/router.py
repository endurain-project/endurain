"""FastAPI router for health fasting endpoints.

This module defines the API endpoints for managing fasting sessions,
including CRUD operations, active fast tracking, and statistics.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security, status

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_fasting.service as health_fasting_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=health_fasting_schema.HealthFastingListResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_fasting_all_pagination(
    _validate_pagination_values_on_query: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values_on_query)
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
) -> health_fasting_schema.HealthFastingListResponse:
    """Retrieve health fasting records for the authenticated user.

    This endpoint fetches health fasting data with optional pagination and
    filtering. Access is restricted to users with the 'health:read' scope.

    Args:
        _validate_pagination_values_on_query: Dependency that validates
            pagination parameters.
        token_user_id: The ID of the authenticated user extracted from the
            access token.
        db: Database session for executing queries.
        page_number: Optional pagination page number to retrieve specific page
            of results.
        num_records: Optional number of records per page for pagination.
        interval: Optional filter to retrieve records within a specific goal
            interval.

    Returns:
        HealthFastingListResponse: A response object containing:
            - total: Total count of records matching the filter criteria
            - num_records: Number of records returned per page
            - page_number: Current page number
            - records: List of paginated HealthFastingRead objects
    Raises:
        HTTPException: If the user lacks required 'health:read' scope or if
            pagination values are invalid.
    """
    return health_fasting_service.list_health_fasting(token_user_id, db, page_number, num_records, interval)


@router.get(
    "/active",
    response_model=health_fasting_schema.HealthFastingRead | None,
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_active_fasting(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_fasting_schema.HealthFastingRead | None:
    """Retrieve the active fasting session for the authenticated user.

    Args:
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Active HealthFastingRead if exists, None otherwise.
    """
    return health_fasting_service.get_active_fasting(token_user_id, db)


@router.get(
    "/stats",
    response_model=health_fasting_schema.HealthFastingStatsResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_fasting_stats(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_fasting_schema.HealthFastingStatsResponse:
    """Retrieve fasting statistics for the authenticated user.

    Args:
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        HealthFastingStatsResponse with statistics.
    """
    return health_fasting_service.get_fasting_stats(token_user_id, db)


@router.get(
    "/{health_fasting_id}",
    response_model=health_fasting_schema.HealthFastingRead,
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_fasting_by_id(
    health_fasting_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_fasting_schema.HealthFastingRead:
    """Retrieve a specific fasting record by ID.

    Args:
        health_fasting_id: ID of the fasting record.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        HealthFastingRead for the specified record.

    Raises:
        NotFoundError: If record not found.
    """
    return health_fasting_service.get_health_fasting(token_user_id, health_fasting_id, db)


@router.post(
    "",
    response_model=health_fasting_schema.HealthFastingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_health_fasting(
    request: Request,
    health_fasting: health_fasting_schema.HealthFastingCreate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_fasting_schema.HealthFastingRead:
    """Create a new fasting session.

    Args:
        request: The incoming request, read by the rate limiter.
        health_fasting: Fasting data to create.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Created HealthFastingRead record.

    Raises:
        InvalidInputError: If user already has an active fast.
    """
    return health_fasting_service.create_health_fasting(token_user_id, health_fasting, db)


@router.put(
    "",
    response_model=health_fasting_schema.HealthFastingRead,
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_health_fasting(
    request: Request,
    health_fasting: health_fasting_schema.HealthFastingUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_fasting_schema.HealthFastingRead:
    """Edit an existing fasting record.

    Args:
        request: The incoming request, read by the rate limiter.
        health_fasting: Fasting data to update.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Updated HealthFastingRead record.
    """
    return health_fasting_service.edit_health_fasting(token_user_id, health_fasting, db)


@router.post(
    "/{health_fasting_id}/complete",
    response_model=health_fasting_schema.HealthFastingRead,
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def complete_health_fasting(
    request: Request,
    health_fasting_id: core_dependencies.PositiveId,
    complete_data: health_fasting_schema.HealthFastingComplete,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_fasting_schema.HealthFastingRead:
    """Complete or end a fasting session.

    Args:
        request: The incoming request, read by the rate limiter.
        health_fasting_id: ID of the fasting record to complete.
        complete_data: Completion data with end time and status.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Updated HealthFastingRead record.
    """
    return health_fasting_service.complete_health_fasting(token_user_id, health_fasting_id, complete_data, db)


@router.delete(
    "/{health_fasting_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_health_fasting(
    request: Request,
    health_fasting_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Delete a fasting record.

    Args:
        request: The incoming request, read by the rate limiter.
        health_fasting_id: ID of the fasting record to delete.
        token_user_id: User ID from the access token.
        db: Database session dependency.
    """
    health_fasting_service.delete_health_fasting(token_user_id, health_fasting_id, db)
