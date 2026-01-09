from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security, status
from sqlalchemy.orm import Session

import health.health_sleep.schema as health_sleep_schema
import health.health_sleep.crud as health_sleep_crud
import health.health_sleep.sleep_scoring as health_sleep_sleep_scoring

import auth.security as auth_security

import core.database as core_database
import core.dependencies as core_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=health_sleep_schema.HealthSleepListResponse,
    status_code=status.HTTP_200_OK,
)
async def read_health_sleep_all(
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["health:read"])
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_sleep_schema.HealthSleepListResponse:
    """
    Retrieve all health sleep records for the authenticated user.

    This endpoint fetches all sleep tracking records associated with the authenticated
    user's ID from the database.

    Args:
        _check_scopes: Security dependency that validates the user has 'health:read' scope.
        token_user_id: The user ID extracted from the JWT access token.
        db: Database session dependency for executing queries.

    Returns:
        HealthSleepListResponse: A response object containing:
            - total (int): The total count of sleep records for the user.
            - records (list): A list of all sleep record objects for the user.

    Raises:
        HTTPException: If authentication fails or user lacks required scopes.
    """
    # Get the total count and records from the database
    total = health_sleep_crud.get_health_sleep_number(token_user_id, db)
    records = health_sleep_crud.get_all_health_sleep_by_user_id(token_user_id, db)

    # Pydantic will convert ORM models to HealthSleepRead via from_attributes=True
    return health_sleep_schema.HealthSleepListResponse(
        total=total, records=records  # type: ignore[arg-type]
    )


@router.get(
    "/page_number/{page_number}/num_records/{num_records}",
    response_model=health_sleep_schema.HealthSleepListResponse,
    status_code=status.HTTP_200_OK,
)
async def read_health_sleep_all_pagination(
    page_number: int,
    num_records: int,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["health:read"])
    ],
    _validate_pagination_values: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values)
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_sleep_schema.HealthSleepListResponse:
    """
    Retrieve all health sleep records for a user with pagination.

    This endpoint fetches paginated health sleep records for the authenticated user.
    It requires 'health:read' scope and validates pagination parameters.

    Args:
        page_number (int): The page number to retrieve (1-indexed).
        num_records (int): The number of records to return per page.
        _check_scopes (Callable): Dependency that validates the required OAuth scopes.
        _validate_pagination_values (Callable): Dependency that validates pagination parameters.
        token_user_id (int): The user ID extracted from the access token.
        db (Session): Database session dependency.

    Returns:
        HealthSleepListResponse: Response containing:
            - total (int): Total number of health sleep records for the user.
            - num_records (int): Number of records returned in this response.
            - page_number (int): Page number of the current response.
            - records (list): List of health sleep records for the requested page.

    Raises:
        HTTPException: If authentication fails or required scopes are missing.
        HTTPException: If pagination values are invalid.
    """
    # Get the total count and records from the database
    total = health_sleep_crud.get_health_sleep_number(token_user_id, db)
    records = health_sleep_crud.get_health_sleep_with_pagination(
        token_user_id, db, page_number, num_records
    )

    # Pydantic will convert ORM models to HealthSleepRead via from_attributes=True
    return health_sleep_schema.HealthSleepListResponse(
        total=total,
        num_records=num_records,
        page_number=page_number,
        records=records,  # type: ignore[arg-type]
    )


@router.post(
    "",
    response_model=health_sleep_schema.HealthSleepRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_health_sleep(
    health_sleep: health_sleep_schema.HealthSleepCreate,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["health:write"])
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_sleep_schema.HealthSleepRead:
    """
    Create or update health sleep data for a user.

    This endpoint creates new health sleep data or updates existing data if an entry
    for the specified date already exists. The operation is determined automatically
    based on whether sleep data exists for the given date.

    Args:
        health_sleep (health_sleep_schema.HealthSleepCreate): The health sleep data to create
            or update, including the date and sleep duration.
        _check_scopes (Callable): Security dependency that verifies the user has
            'health:write' scope.
        token_user_id (int): The ID of the authenticated user extracted from the
            access token.
        db (Session): Database session dependency for database operations.

    Returns:
        health_sleep_schema.HealthSleepRead: The created or updated health sleep data.

    Raises:
        HTTPException: 400 error if the date field is not provided in the request.
    """
    # Calculate sleep scores before saving
    health_sleep_sleep_scoring._calculate_and_set_sleep_scores(health_sleep)

    # Date is guaranteed to be present due to HealthSleepCreate validator
    date_str = health_sleep.date.isoformat()  # type: ignore[union-attr]

    # Check if health_sleep for this date already exists
    sleep_for_date = health_sleep_crud.get_health_sleep_by_date(
        token_user_id, date_str, db
    )

    if sleep_for_date:
        # Convert to update schema with the existing ID
        health_sleep_update = health_sleep_schema.HealthSleepUpdate(
            id=sleep_for_date.id, **health_sleep.model_dump()
        )
        # Updates the health_sleep in the database and returns it
        return health_sleep_crud.edit_health_sleep(
            token_user_id, health_sleep_update, db
        )
    else:
        # Creates the health_sleep in the database and returns it
        return health_sleep_crud.create_health_sleep(token_user_id, health_sleep, db)


@router.put(
    "",
    response_model=health_sleep_schema.HealthSleepRead,
    status_code=status.HTTP_200_OK,
)
async def edit_health_sleep(
    health_sleep: health_sleep_schema.HealthSleepUpdate,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["health:write"])
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_sleep_schema.HealthSleepRead:
    """
    Edit health sleep data for a user.

    This endpoint updates existing health sleep records in the database for the authenticated user.
    Requires 'health:write' scope for authorization.

    Args:
        health_sleep (health_sleep_schema.HealthSleepUpdate): The health sleep data to be updated,
            containing the new values for the health sleep record.
        _check_scopes (Callable): Security dependency that verifies the user has 'health:write'
            scope permission.
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
    # Recalculate sleep scores when editing
    health_sleep_sleep_scoring._calculate_and_set_sleep_scores(health_sleep)

    # Updates the health_sleep in the database and returns it
    return health_sleep_crud.edit_health_sleep(token_user_id, health_sleep, db)


@router.delete(
    "/{health_sleep_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT
)
async def delete_health_sleep(
    health_sleep_id: int,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["health:write"])
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """
    Delete a health sleep record for the authenticated user.

    This endpoint removes a specific health sleep entry from the database for the user
    identified by the access token. The user must have 'health:write' scope permission.

    Args:
        health_sleep_id (int): The unique identifier of the health sleep record to delete.
        _check_scopes (Callable): Security dependency that verifies the user has 'health:write' scope.
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
    health_sleep_crud.delete_health_sleep(token_user_id, health_sleep_id, db)
