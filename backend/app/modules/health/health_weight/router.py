from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.schema as health_weight_schema

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
    """
    Retrieve paginated health weight records for the authenticated user.

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
    # Get the total count and paginated records from the database
    total = health_weight_crud.get_health_weight_number_by_user_id(token_user_id, db, interval)
    records = health_weight_crud.get_health_weight_by_user_id(token_user_id, db, page_number, num_records, interval)

    # Pydantic will convert ORM models to HealthStepsRead via from_attributes=True
    return health_weight_schema.HealthWeightListResponse(
        total=total,
        num_records=num_records,
        page_number=page_number,
        records=records,
    )


@router.post(
    "",
    response_model=health_weight_schema.HealthWeightRead,
    status_code=status.HTTP_201_CREATED,
)
def create_health_weight(
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
    """
    Create or update a health weight record for the authenticated user.

    This endpoint creates a new health weight record if one doesn't exist for the given date,
    or updates an existing record if one is already present for that date.

    Args:
        health_weight (health_weight_schema.HealthWeightCreate): The health weight data to create or update.
            Must include a date field.
        _check_scopes (Callable): Security dependency that verifies the user has 'health:write' scope.
        token_user_id (int): The ID of the authenticated user extracted from the access token.
        db (Session): Database session dependency for performing database operations.

    Returns:
        health_weight_schema.HealthWeightRead: The created or updated health weight record.

    Raises:
        HTTPException: 400 error if the date field is not provided in the request.
    """
    if not health_weight.date:
        raise HTTPException(status_code=400, detail="Date field is required.")

    # Convert date to string format for CRUD function
    date_str = health_weight.date.isoformat()

    # Check if health_weight for this date already exists
    health_for_date = health_weight_crud.get_health_weight_by_date_and_user_id(token_user_id, date_str, db)

    if health_for_date:
        # Convert to update schema with the existing ID
        health_weight_update = health_weight_schema.HealthWeightUpdate(
            id=health_for_date.id,
            user_id=token_user_id,
            **health_weight.model_dump(),
        )
        # Updates the health_weight in the database and returns it
        return health_weight_crud.edit_health_weight(token_user_id, health_weight_update, db)
    else:
        # Creates the health_weight in the database and returns it
        return health_weight_crud.create_health_weight(token_user_id, health_weight, db)


@router.put(
    "",
    response_model=health_weight_schema.HealthWeightRead,
    status_code=status.HTTP_200_OK,
)
def edit_health_weight(
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
    """
    Edit a health weight entry for the authenticated user.

    This endpoint allows users with 'health:write' scope to update an existing
    health weight record in the database.

    Args:
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
        HTTPException: If the user doesn't have permission to edit the weight entry
            or if the entry doesn't exist.
    """
    # Updates the health_weight in the database and returns it
    return health_weight_crud.edit_health_weight(token_user_id, health_weight, db)


@router.delete("/{health_weight_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def delete_health_weight(
    health_weight_id: int,
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
    Delete a health weight entry for the authenticated user.

    This endpoint allows users to delete their own health weight records. It requires
    the 'health:write' scope for authorization.

    Args:
        health_weight_id (int): The unique identifier of the health weight entry to delete.
        _check_scopes (Callable): Security dependency that verifies the user has 'health:write' scope.
        token_user_id (int): The user ID extracted from the access token, used to ensure
            users can only delete their own weight entries.
        db (Session): Database session dependency for performing database operations.

    Returns:
        None: This function does not return any value upon successful deletion.

    Raises:
        HTTPException: May raise various HTTP exceptions (e.g., 404 if entry not found,
            403 if unauthorized) through the CRUD layer.
    """
    # Deletes entry from database
    health_weight_crud.delete_health_weight(token_user_id, health_weight_id, db)
