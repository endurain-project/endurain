"""FastAPI router for health poop (bowel movement) endpoints.

This module defines the API endpoints for managing bowel movement
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
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_poop.schema as health_poop_schema
import modules.health.health_poop.service as health_poop_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=(health_poop_schema.HealthPoopListResponse),
    status_code=status.HTTP_200_OK,
)
def read_health_poop_all_pagination(
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:read"],
        ),
    ],
    _validate_pagination_values_on_query: Annotated[
        Callable,
        Depends(core_dependencies.validate_pagination_values_on_query),
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
) -> health_poop_schema.HealthPoopListResponse:
    """Retrieve paginated poop records for the user.

    Args:
        _check_scopes: Security dependency that validates the
            user has 'health:read' scope.
        _validate_pagination_values_on_query: Dependency that
            validates pagination parameters.
        token_user_id: The ID of the authenticated user
            extracted from the access token.
        db: Database session for executing queries.
        page_number: Optional pagination page number.
        num_records: Optional number of records per page.
        interval: Optional filter by goal interval.

    Returns:
        HealthPoopListResponse containing total count,
            pagination info, and poop records.

    Raises:
        HTTPException: If the user lacks required scope or
            pagination values are invalid.
    """
    return health_poop_service.list_health_poop(token_user_id, db, page_number, num_records, interval)


@router.get(
    "/{health_poop_id}",
    response_model=health_poop_schema.HealthPoopRead,
    status_code=status.HTTP_200_OK,
)
def read_health_poop_by_id(
    health_poop_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:read"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_poop_schema.HealthPoopRead:
    """Retrieve a specific poop record by ID.

    Args:
        health_poop_id: ID of the poop record.
        _check_scopes: Security dependency for health:read.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        HealthPoopRead for the specified record.

    Raises:
        HTTPException: If record not found.
    """
    return health_poop_service.get_health_poop(token_user_id, health_poop_id, db)


@router.post(
    "",
    response_model=health_poop_schema.HealthPoopRead,
    status_code=status.HTTP_201_CREATED,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_health_poop(
    request: Request,
    health_poop: health_poop_schema.HealthPoopCreate,
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:write"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_poop_schema.HealthPoopRead:
    """Create a new poop record for the user.

    Unlike other health modules, multiple poop records can exist
    per day.

    Args:
        request: The incoming request, read by the rate limiter.
        health_poop: Poop data to create.
        _check_scopes: Security dependency for health:write.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Created HealthPoopRead record.
    """
    return health_poop_service.create_health_poop(token_user_id, health_poop, db)


@router.put(
    "",
    response_model=health_poop_schema.HealthPoopRead,
    status_code=status.HTTP_200_OK,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_health_poop(
    request: Request,
    health_poop: health_poop_schema.HealthPoopUpdate,
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:write"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_poop_schema.HealthPoopRead:
    """Edit an existing poop record.

    Args:
        request: The incoming request, read by the rate limiter.
        health_poop: Poop data to update.
        _check_scopes: Security dependency for health:write.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Updated HealthPoopRead record.

    Raises:
        HTTPException: If record not found or unauthorized.
    """
    return health_poop_service.edit_health_poop(token_user_id, health_poop, db)


@router.delete(
    "/{health_poop_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_health_poop(
    request: Request,
    health_poop_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:write"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """Delete a poop record for the authenticated user.

    Args:
        request: The incoming request, read by the rate limiter.
        health_poop_id: ID of the poop record to delete.
        _check_scopes: Security dependency for health:write.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Raises:
        HTTPException: If record not found or unauthorized.
    """
    health_poop_service.delete_health_poop(token_user_id, health_poop_id, db)
