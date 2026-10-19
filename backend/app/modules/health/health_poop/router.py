"""
FastAPI router for health poop (bowel movement) endpoints.

This module defines the API endpoints for managing bowel movement
records, including CRUD operations with pagination and filtering.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Security,
    status,
)
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_poop.crud as health_poop_crud
import modules.health.health_poop.schema as health_poop_schema

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
    """
    Retrieve paginated poop records for the user.

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
    total = health_poop_crud.get_health_poop_number_by_user_id(token_user_id, db, interval)
    records = health_poop_crud.get_health_poop_by_user_id(
        token_user_id,
        db,
        page_number,
        num_records,
        interval,
    )

    return health_poop_schema.HealthPoopListResponse(
        total=total,
        num_records=num_records,
        page_number=page_number,
        records=records,
    )


@router.get(
    "/{health_poop_id}",
    response_model=health_poop_schema.HealthPoopRead,
    status_code=status.HTTP_200_OK,
)
def read_health_poop_by_id(
    health_poop_id: int,
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
    """
    Retrieve a specific poop record by ID.

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
    record = health_poop_crud.get_health_poop_by_id_and_user_id(health_poop_id, token_user_id, db)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Poop record not found",
        )

    return record  # type: ignore[return-value]


@router.post(
    "",
    response_model=health_poop_schema.HealthPoopRead,
    status_code=status.HTTP_201_CREATED,
)
def create_health_poop(
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
    """
    Create a new poop record for the user.

    Unlike other health modules, multiple poop records can exist
    per day.

    Args:
        health_poop: Poop data to create.
        _check_scopes: Security dependency for health:write.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Created HealthPoopRead record.
    """
    return health_poop_crud.create_health_poop(token_user_id, health_poop, db)


@router.put(
    "",
    response_model=health_poop_schema.HealthPoopRead,
    status_code=status.HTTP_200_OK,
)
def edit_health_poop(
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
    """
    Edit an existing poop record.

    Args:
        health_poop: Poop data to update.
        _check_scopes: Security dependency for health:write.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Updated HealthPoopRead record.

    Raises:
        HTTPException: If record not found or unauthorized.
    """
    return health_poop_crud.edit_health_poop(token_user_id, health_poop, db)


@router.delete(
    "/{health_poop_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_health_poop(
    health_poop_id: int,
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
    """
    Delete a poop record for the authenticated user.

    Args:
        health_poop_id: ID of the poop record to delete.
        _check_scopes: Security dependency for health:write.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Raises:
        HTTPException: If record not found or unauthorized.
    """
    health_poop_crud.delete_health_poop(token_user_id, health_poop_id, db)
