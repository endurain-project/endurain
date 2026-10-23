"""FastAPI router for health weight endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_weight.schema as health_weight_schema
import modules.health.health_weight.service as health_weight_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=health_weight_schema.HealthWeightListResponse,
    status_code=status.HTTP_200_OK,
)
def read_health_weight_all_pagination(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:read"])],
    _validate_pagination_values_on_query: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values_on_query)
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
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
) -> health_weight_schema.HealthWeightListResponse:
    """Retrieve paginated health weight records for the authenticated user.

    This endpoint fetches health weight data with optional pagination and
    filtering. Access is restricted to users with the 'health:read' scope.

    Args:
        _check_scopes: Security dependency that validates the user has
            'health:read' scope.
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
        HealthWeightListResponse: A response object containing:
            - total: Total count of records matching the filter criteria
            - num_records: Number of records returned per page
            - page_number: Current page number
            - records: List of paginated HealthWeightRead objects

    Raises:
        HTTPException: If the user lacks required 'health:read' scope or if
            pagination values are invalid.
    """
    return health_weight_service.list_health_weight(token_user_id, db, page_number, num_records, interval)


@router.post(
    "",
    response_model=health_weight_schema.HealthWeightRead,
    status_code=status.HTTP_201_CREATED,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_health_weight(
    request: Request,
    health_weight: health_weight_schema.HealthWeightCreate,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_weight_schema.HealthWeightRead:
    """Create or update a health weight record for the authenticated user.

    This endpoint creates a new health weight record if one doesn't exist for the given date,
    or updates an existing record if one is already present for that date.

    Args:
        request: The incoming request, read by the rate limiter.
        health_weight (health_weight_schema.HealthWeightCreate): The health weight data to create or update.
            Must include a date field.
        _check_scopes (Callable): Security dependency that verifies the user has 'health:write' scope.
        token_user_id (int): The ID of the authenticated user extracted from the access token.
        db (Session): Database session dependency for performing database operations.

    Returns:
        health_weight_schema.HealthWeightRead: The created or updated health weight record.

    """
    return health_weight_service.create_health_weight(token_user_id, health_weight, db)


@router.put(
    "",
    response_model=health_weight_schema.HealthWeightRead,
    status_code=status.HTTP_200_OK,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_health_weight(
    request: Request,
    health_weight: health_weight_schema.HealthWeightUpdate,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_weight_schema.HealthWeightRead:
    """Edit a health weight entry for the authenticated user.

    This endpoint allows users with 'health:write' scope to update an existing
    health weight record in the database.

    Args:
        request: The incoming request, read by the rate limiter.
        health_weight (health_weight_schema.HealthWeight): The health weight data
            to be updated, containing the weight information and associated metadata.
        _check_scopes (Callable): Security dependency that verifies the user has
            'health:write' scope permission.
        token_user_id (int): The ID of the authenticated user extracted from the
            access token.
        db (Session): Database session dependency for executing database operations.

    Returns:
        The updated health weight record from the database.

    Raises:
        PermissionDeniedError: If the record names another user.
        NotFoundError: If the entry doesn't exist.
    """
    return health_weight_service.edit_health_weight(token_user_id, health_weight, db)


@router.delete("/{health_weight_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_health_weight(
    request: Request,
    health_weight_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """Delete a health weight entry for the authenticated user.

    This endpoint allows users to delete their own health weight records. It requires
    the 'health:write' scope for authorization.

    Args:
        request: The incoming request, read by the rate limiter.
        health_weight_id (int): The unique identifier of the health weight entry to delete.
        _check_scopes (Callable): Security dependency that verifies the user has 'health:write' scope.
        token_user_id (int): The user ID extracted from the access token, used to ensure
            users can only delete their own weight entries.
        db (Session): Database session dependency for performing database operations.

    Returns:
        None: This function does not return any value upon successful deletion.

    Raises:
        NotFoundError: If the entry doesn't exist for the user.
    """
    health_weight_service.delete_health_weight(token_user_id, health_weight_id, db)
