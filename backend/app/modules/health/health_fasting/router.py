"""
FastAPI router for health fasting endpoints.

This module defines the API endpoints for managing fasting sessions,
including CRUD operations, active fast tracking, and statistics.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_fasting.utils as health_fasting_utils

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=health_fasting_schema.HealthFastingListResponse,
    status_code=status.HTTP_200_OK,
)
def read_health_fasting_all_pagination(
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
) -> health_fasting_schema.HealthFastingListResponse:
    """
    Retrieve health fasting records for the authenticated user.

    This endpoint fetches health fasting data with optional pagination and
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
        HealthFastingListResponse: A response object containing:
            - total: Total count of records matching the filter criteria
            - num_records: Number of records returned per page
            - page_number: Current page number
            - records: List of paginated HealthFastingRead objects
    Raises:
        HTTPException: If the user lacks required 'health:read' scope or if
            pagination values are invalid.
    """
    total = health_fasting_crud.get_health_fasting_number_by_user_id(token_user_id, db, interval)
    records = health_fasting_crud.get_health_fasting_by_user_id(token_user_id, db, page_number, num_records, interval)

    return health_fasting_schema.HealthFastingListResponse(
        total=total,
        num_records=num_records,
        page_number=page_number,
        records=records,
    )


@router.get(
    "/active",
    response_model=health_fasting_schema.HealthFastingRead | None,
    status_code=status.HTTP_200_OK,
)
def read_active_fasting(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_fasting_schema.HealthFastingRead | None:
    """
    Retrieve the active fasting session for the authenticated user.

    Args:
        _check_scopes: Security dependency for health:read scope.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Active HealthFastingRead if exists, None otherwise.
    """
    return health_fasting_crud.get_active_fasting_by_user_id(token_user_id, db)


@router.get(
    "/stats",
    response_model=health_fasting_schema.HealthFastingStatsResponse,
    status_code=status.HTTP_200_OK,
)
def read_fasting_stats(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_fasting_schema.HealthFastingStatsResponse:
    """
    Retrieve fasting statistics for the authenticated user.

    Args:
        _check_scopes: Security dependency for health:read scope.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        HealthFastingStatsResponse with statistics.
    """
    total_fasts = health_fasting_crud.get_completed_fasting_count(token_user_id, db)
    total_fasting_seconds = health_fasting_crud.get_total_fasting_seconds(token_user_id, db)
    avg_duration = health_fasting_crud.get_avg_fasting_duration(token_user_id, db)

    # Calculate streaks
    current_streak, longest_streak = health_fasting_utils.calculate_streaks(token_user_id, db)

    # Calculate completion rate
    total_started = health_fasting_crud.get_health_fasting_number_by_user_id(token_user_id, db)
    completion_rate = (total_fasts / total_started * 100) if total_started > 0 else 0.0

    return health_fasting_schema.HealthFastingStatsResponse(
        total_fasts=total_fasts,
        current_streak=current_streak,
        longest_streak=longest_streak,
        avg_duration_seconds=avg_duration,
        total_fasting_seconds=total_fasting_seconds,
        completion_rate=round(completion_rate, 1),
    )


@router.get(
    "/{health_fasting_id}",
    response_model=health_fasting_schema.HealthFastingRead,
    status_code=status.HTTP_200_OK,
)
def read_health_fasting_by_id(
    health_fasting_id: int,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_fasting_schema.HealthFastingRead:
    """
    Retrieve a specific fasting record by ID.

    Args:
        health_fasting_id: ID of the fasting record.
        _check_scopes: Security dependency for health:read scope.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        HealthFastingRead for the specified record.

    Raises:
        HTTPException: If record not found.
    """
    record = health_fasting_crud.get_health_fasting_by_id_and_user_id(health_fasting_id, token_user_id, db)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fasting record not found",
        )

    return record  # type: ignore[return-value]


@router.post(
    "",
    response_model=health_fasting_schema.HealthFastingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_health_fasting(
    health_fasting: health_fasting_schema.HealthFastingCreate,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_fasting_schema.HealthFastingRead:
    """
    Create a new fasting session.

    Args:
        health_fasting: Fasting data to create.
        _check_scopes: Security dependency for health:write scope.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Created HealthFastingRead record.

    Raises:
        HTTPException: If user already has an active fast.
    """
    # Check if user already has an active fast
    active_fast = health_fasting_crud.get_active_fasting_by_user_id(token_user_id, db)

    if active_fast is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has an active fasting session. Complete or cancel it before starting a new one.",
        )

    return health_fasting_crud.create_health_fasting(token_user_id, health_fasting, db)


@router.put(
    "",
    response_model=health_fasting_schema.HealthFastingRead,
    status_code=status.HTTP_200_OK,
)
def edit_health_fasting(
    health_fasting: health_fasting_schema.HealthFastingUpdate,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_fasting_schema.HealthFastingRead:
    """
    Edit an existing fasting record.

    Args:
        health_fasting: Fasting data to update.
        _check_scopes: Security dependency for health:write scope.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Updated HealthFastingRead record.
    """
    return health_fasting_crud.edit_health_fasting(token_user_id, health_fasting, db)


@router.post(
    "/{health_fasting_id}/complete",
    response_model=health_fasting_schema.HealthFastingRead,
    status_code=status.HTTP_200_OK,
)
def complete_health_fasting(
    health_fasting_id: int,
    complete_data: health_fasting_schema.HealthFastingComplete,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_fasting_schema.HealthFastingRead:
    """
    Complete or end a fasting session.

    Args:
        health_fasting_id: ID of the fasting record to complete.
        complete_data: Completion data with end time and status.
        _check_scopes: Security dependency for health:write scope.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Updated HealthFastingRead record.
    """
    return health_fasting_crud.complete_health_fasting(token_user_id, health_fasting_id, complete_data, db)


@router.delete(
    "/{health_fasting_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_health_fasting(
    health_fasting_id: int,
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
    """
    Delete a fasting record.

    Args:
        health_fasting_id: ID of the fasting record to delete.
        _check_scopes: Security dependency for health:write scope.
        token_user_id: User ID from the access token.
        db: Database session dependency.
    """
    health_fasting_crud.delete_health_fasting(token_user_id, health_fasting_id, db)
