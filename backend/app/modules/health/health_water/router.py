"""
FastAPI router for health water intake endpoints.

This module defines the API endpoints for managing water intake
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
import modules.health.health_water.crud as health_water_crud
import modules.health.health_water.schema as health_water_schema

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=(health_water_schema.HealthWaterListResponse),
    status_code=status.HTTP_200_OK,
)
def read_health_water_all_pagination(
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
) -> health_water_schema.HealthWaterListResponse:
    """
    Retrieve paginated water intake records for the user.

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
        HealthWaterListResponse containing total count,
            pagination info, and water intake records.

    Raises:
        HTTPException: If the user lacks required scope or
            pagination values are invalid.
    """
    total = health_water_crud.get_health_water_number_by_user_id(token_user_id, db, interval)
    records = health_water_crud.get_health_water_by_user_id(
        token_user_id,
        db,
        page_number,
        num_records,
        interval,
    )

    return health_water_schema.HealthWaterListResponse(
        total=total,
        num_records=num_records,
        page_number=page_number,
        records=records,
    )


@router.post(
    "",
    response_model=health_water_schema.HealthWaterRead,
    status_code=status.HTTP_201_CREATED,
)
def create_health_water(
    health_water: health_water_schema.HealthWaterCreate,
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
) -> health_water_schema.HealthWaterRead:
    """
    Create or update a water intake record for the user.

    If a record already exists for the given date, it will be
    updated instead of creating a duplicate.

    Args:
        health_water: Water intake data to create.
        _check_scopes: Security dependency for health:write.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Created or updated HealthWaterRead record.

    Raises:
        HTTPException: 400 if date field is not provided.
    """
    if not health_water.date:
        raise HTTPException(
            status_code=400,
            detail="Date field is required.",
        )

    date_str = health_water.date.isoformat()

    water_for_date = health_water_crud.get_health_water_by_date_and_user_id(token_user_id, date_str, db)

    if water_for_date:
        accumulated_ml = (water_for_date.amount_ml or 0) + (health_water.amount_ml or 0)
        health_water_update = health_water_schema.HealthWaterUpdate(
            id=water_for_date.id,
            user_id=token_user_id,
            amount_ml=accumulated_ml,
            date=health_water.date,
            source=health_water.source,
        )
        return health_water_crud.edit_health_water(token_user_id, health_water_update, db)
    else:
        return health_water_crud.create_health_water(token_user_id, health_water, db)


@router.put(
    "",
    response_model=health_water_schema.HealthWaterRead,
    status_code=status.HTTP_200_OK,
)
def edit_health_water(
    health_water: health_water_schema.HealthWaterUpdate,
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
) -> health_water_schema.HealthWaterRead:
    """
    Edit an existing water intake record.

    Args:
        health_water: Water intake data to update.
        _check_scopes: Security dependency for health:write.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Updated HealthWaterRead record.

    Raises:
        HTTPException: If record not found or unauthorized.
    """
    return health_water_crud.edit_health_water(token_user_id, health_water, db)


@router.delete(
    "/{health_water_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_health_water(
    health_water_id: int,
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
    Delete a water intake record for the authenticated user.

    Args:
        health_water_id: ID of the water intake record.
        _check_scopes: Security dependency for health:write.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Raises:
        HTTPException: If record not found or unauthorized.
    """
    health_water_crud.delete_health_water(token_user_id, health_water_id, db)
