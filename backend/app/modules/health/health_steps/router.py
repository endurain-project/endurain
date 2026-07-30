from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.schema as health_steps_schema

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=health_steps_schema.HealthStepsListResponse,
    status_code=status.HTTP_200_OK,
)
def read_health_steps_all_pagination(
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
) -> health_steps_schema.HealthStepsListResponse:
    """
    Retrieve paginated health steps records for the authenticated user.

    This endpoint fetches health steps data with optional pagination and
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
        HealthStepsListResponse: A response object containing:
            - total: Total count of records matching the filter criteria
            - num_records: Number of records returned per page
            - page_number: Current page number
            - records: List of paginated HealthStepsRead objects
    Raises:
        HTTPException: If the user lacks required 'health:read' scope or if
            pagination values are invalid.
    """
    # Get the total count and paginated records from the database
    total = health_steps_crud.get_health_steps_number_by_user_id(token_user_id, db, interval)
    records = health_steps_crud.get_health_steps_by_user_id(token_user_id, db, page_number, num_records, interval)

    # Pydantic will convert ORM models to HealthStepsRead via from_attributes=True
    return health_steps_schema.HealthStepsListResponse(
        total=total,
        num_records=num_records,
        page_number=page_number,
        records=records,
    )


@router.post(
    "",
    response_model=health_steps_schema.HealthStepsRead,
    status_code=status.HTTP_201_CREATED,
)
def create_health_steps(
    health_steps: health_steps_schema.HealthStepsCreate,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_steps_schema.HealthStepsRead:
    """
    Create or update health steps data for a user.

    This endpoint creates new health steps data or updates existing data if an entry
    for the specified date already exists. The operation is determined automatically
    based on whether steps data exists for the given date.

    Args:
        health_steps (health_steps_schema.HealthSteps): The health steps data to create
            or update, including the date and step count.
        _check_scopes (Callable): Security dependency that verifies the user has
            'health:write' scope.
        token_user_id (int): The ID of the authenticated user extracted from the
            access token.
        db (Session): Database session dependency for database operations.

    Returns:
        health_steps_schema.HealthSteps: The created or updated health steps data.

    Raises:
        HTTPException: 400 error if the date field is not provided in the request.
    """
    if not health_steps.date:
        raise HTTPException(status_code=400, detail="Date field is required.")

    # Convert date to string format for CRUD function
    date_str = health_steps.date.isoformat()

    # Check if health_steps for this date already exists
    steps_for_date = health_steps_crud.get_health_steps_by_date_and_user_id(token_user_id, date_str, db)

    if steps_for_date:
        # Convert to update schema with the existing ID and user_id
        health_steps_update = health_steps_schema.HealthStepsUpdate(
            id=steps_for_date.id, user_id=token_user_id, **health_steps.model_dump()
        )
        # Updates the health_steps in the database and returns it
        return health_steps_crud.edit_health_steps(token_user_id, health_steps_update, db)
    else:
        # Creates the health_steps in the database and returns it
        return health_steps_crud.create_health_steps(token_user_id, health_steps, db)


@router.put(
    "",
    response_model=health_steps_schema.HealthStepsRead,
    status_code=status.HTTP_200_OK,
)
def edit_health_steps(
    health_steps: health_steps_schema.HealthStepsUpdate,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_steps_schema.HealthStepsRead:
    """
    Edit health steps data for a user.

    This endpoint updates existing health steps records in the database for the authenticated user.
    Requires 'health:write' scope for authorization.

    Args:
        health_steps (health_steps_schema.HealthSteps): The health steps data to be updated,
            containing the new values for the health steps record.
        _check_scopes (Callable): Security dependency that verifies the user has 'health:write'
            scope permission.
        token_user_id (int): The user ID extracted from the JWT access token, used to identify
            the user making the request.
        db (Session): Database session dependency for performing database operations.

    Returns:
        health_steps_schema.HealthSteps: The updated health steps record with the new values
            as stored in the database.

    Raises:
        HTTPException: May raise various HTTP exceptions if authorization fails, user is not
            found, or database operations fail.
    """
    # Updates the health_steps in the database and returns it
    return health_steps_crud.edit_health_steps(token_user_id, health_steps, db)


@router.delete("/{health_steps_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def delete_health_steps(
    health_steps_id: int,
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
    Delete a health steps record for the authenticated user.

    This endpoint removes a specific health steps entry from the database for the user
    identified by the access token. The user must have 'health:write' scope permission.

    Args:
        health_steps_id (int): The unique identifier of the health steps record to delete.
        _check_scopes (Callable): Security dependency that verifies the user has 'health:write' scope.
        token_user_id (int): The user ID extracted from the access token.
        db (Session): Database session dependency for executing the delete operation.

    Returns:
        None: This function does not return a value.

    Raises:
        HTTPException: May be raised by dependencies if:
            - The access token is invalid or expired
            - The user lacks required 'health:write' scope
            - The health steps record doesn't exist or doesn't belong to the user
    """
    # Deletes entry from database
    health_steps_crud.delete_health_steps(token_user_id, health_steps_id, db)
