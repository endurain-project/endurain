"""FastAPI router for health sleep endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security, status

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_sleep.service as health_sleep_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=health_sleep_schema.HealthSleepListResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_sleep_all_pagination(
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
) -> health_sleep_schema.HealthSleepListResponse:
    """Retrieve health sleep records for the authenticated user.

    This endpoint fetches health sleep data with optional pagination and
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
        HealthSleepListResponse: A response object containing:
            - total: Total count of records matching the filter criteria
            - num_records: Number of records returned per page
            - page_number: Current page number
            - records: List of paginated HealthSleepRead objects
    Raises:
        HTTPException: If the user lacks required 'health:read' scope or if
            pagination values are invalid.
    """
    return health_sleep_service.list_health_sleep(token_user_id, db, page_number, num_records, interval)


@router.post(
    "",
    response_model=health_sleep_schema.HealthSleepRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_health_sleep(
    request: Request,
    health_sleep: health_sleep_schema.HealthSleepCreate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_sleep_schema.HealthSleepRead:
    """Create or update health sleep data for a user.

    This endpoint creates new health sleep data or updates existing data if an entry
    for the specified date already exists. The operation is determined automatically
    based on whether sleep data exists for the given date.

    Args:
        request: The incoming request, read by the rate limiter.
        health_sleep (health_sleep_schema.HealthSleepCreate): The health sleep data to create
            or update, including the date and sleep duration.
        token_user_id (int): The ID of the authenticated user extracted from the
            access token.
        db (Session): Database session dependency for database operations.

    Returns:
        health_sleep_schema.HealthSleepRead: The created or updated health sleep data.

    """
    return health_sleep_service.create_health_sleep(token_user_id, health_sleep, db)


@router.put(
    "",
    response_model=health_sleep_schema.HealthSleepRead,
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_health_sleep(
    request: Request,
    health_sleep: health_sleep_schema.HealthSleepUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_sleep_schema.HealthSleepRead:
    """Edit health sleep data for a user.

    This endpoint updates existing health sleep records in the database for the authenticated user.
    Requires 'health:write' scope for authorization.

    Args:
        request: The incoming request, read by the rate limiter.
        health_sleep (health_sleep_schema.HealthSleepUpdate): The health sleep data to be updated,
            containing the new values for the health sleep record.
        token_user_id (int): The user ID extracted from the JWT access token, used to identify
            the user making the request.
        db (Session): Database session dependency for performing database operations.

    Returns:
        health_sleep_schema.HealthSleepRead: The updated health sleep record with the new values
            as stored in the database.

    Raises:
        HTTPException: May raise various HTTP exceptions if authorization fails, user is not
            found, or database operations fail.
    """
    return health_sleep_service.edit_health_sleep(token_user_id, health_sleep, db)


@router.delete(
    "/{health_sleep_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_health_sleep(
    request: Request,
    health_sleep_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Delete a health sleep record for the authenticated user.

    This endpoint removes a specific health sleep entry from the database for the user
    identified by the access token. The user must have 'health:write' scope permission.

    Args:
        request: The incoming request, read by the rate limiter.
        health_sleep_id (int): The unique identifier of the health sleep record to delete.
        token_user_id (int): The user ID extracted from the access token.
        db (Session): Database session dependency for executing the delete operation.

    Returns:
        None: This function does not return a value.

    Raises:
        HTTPException: May be raised by dependencies if:
            - The access token is invalid or expired
            - The user lacks required 'health:write' scope
            - The health sleep record doesn't exist or doesn't belong to the user
    """
    # Deletes entry from database
    health_sleep_service.delete_health_sleep(token_user_id, health_sleep_id, db)
