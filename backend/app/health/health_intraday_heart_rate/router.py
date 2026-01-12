from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security, HTTPException, status
from sqlalchemy.orm import Session

import health.health_intraday_heart_rate.schema as health_intraday_heart_rate_schema
import health.health_intraday_heart_rate.crud as health_intraday_heart_rate_crud

import auth.security as auth_security

import core.database as core_database
import core.dependencies as core_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=health_intraday_heart_rate_schema.HealthIntradayHeartrateListResponse,
    status_code=status.HTTP_200_OK,
)
async def read_health_intraday_heart_rate_all(
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
) -> health_intraday_heart_rate_schema.HealthIntradayHeartrateListResponse:
    """
    Retrieve all health intraday heart rate records for the authenticated user.

    This endpoint fetches all health intraday heart rate entries associated with the authenticated user's ID.
    It requires the 'health:read' scope for authorization.

    Args:
        _check_scopes (Callable): Security dependency that validates the required scopes.
        token_user_id (int): The user ID extracted from the access token.
        db (Session): Database session dependency for querying the database.

    Returns:
        HealthStepsListResponse: A response object containing:
            - total (int): The total number of health intraday heart rate records for the user.
            - records (List): A list of all health intraday heart rate records for the user.

    Raises:
        HTTPException: May raise authentication or authorization related exceptions
            if the token is invalid or the user lacks required permissions.
    """
    # Get the total count and records from the database
    total = health_intraday_heart_rate_crud.get_health_intraday_heart_rate_number(token_user_id, db)
    records = health_intraday_heart_rate_crud.get_all_health_intraday_heart_rate_by_user_id(token_user_id, db)

    # Pydantic will convert ORM models to HealthStepsRead via from_attributes=True
    return health_intraday_heart_rate_schema.HealthIntradayHeartrateListResponse(
        total=total, records=records  # type: ignore[arg-type]
    )


@router.get(
    "/{date_str}",
    response_model=health_intraday_heart_rate_schema.HealthIntradayHeartrateListResponse,
    status_code=status.HTTP_200_OK,
)
async def read_health_intraday_heart_rate_by_date(
    date_str: str,
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
) -> health_intraday_heart_rate_schema.HealthIntradayHeartrateListResponse:
    """
    Retrieve all health intraday heart rate measurements for the authenticated user and given date.

    This endpoint fetches all health intraday heart rate measurements associated with the authenticated user's ID
    and for the given date. It requires the 'health:read' scope for authorization.

    Args:
        date: The date of interest (in local timezone).
        _check_scopes (Callable): Security dependency that validates the required scopes.
        token_user_id (int): The user ID extracted from the access token.
        db (Session): Database session dependency for querying the database.

    Returns:
        HealthIntradayHeartrateListResponse: A response object containing:
            - records (List): A list of all health intraday heart rate measurements for the user.

    Raises:
        HTTPException: May raise authentication or authorization related exceptions
            if the token is invalid or the user lacks required permissions.
    """
    # Get all records from the database
    records = health_intraday_heart_rate_crud.get_health_intraday_heart_rate_number_by_date(token_user_id, date_str, db)
    
    # Pydantic will convert ORM models to HealthIntradayHeartrateRead via from_attributes=True
    return health_intraday_heart_rate_schema.HealthIntradayHeartrateListResponse(
        records=records, num_records=len(records)  # type: ignore[arg-type]
    )


@router.get(
    "/page_number/{page_number}/num_records/{num_records}",
    response_model=health_intraday_heart_rate_schema.HealthIntradayHeartrateListResponse,
    status_code=status.HTTP_200_OK,
)
async def read_health_intraday_heart_rate_all_pagination(
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
) -> health_intraday_heart_rate_schema.HealthIntradayHeartrateListResponse:
    """
    Retrieve paginated health intraday heart rate records for the authenticated user.

    This endpoint returns a paginated list of health intraday heart rate data for the user identified
    by the access token. It enforces proper authentication, authorization (health:read scope),
    and pagination parameter validation.

    Args:
        page_number (int): The page number to retrieve (1-indexed).
        num_records (int): The number of records per page.
        _check_scopes (Callable): Dependency that validates the user has 'health:read' scope.
        _validate_pagination_values (Callable): Dependency that validates pagination parameters.
        token_user_id (int): The user ID extracted from the access token.
        db (Session): Database session dependency.

    Returns:
        HealthStepsListResponse: A response object containing:
            - total (int): The total number of health intraday heart rate records for the user.
            - num_records (int): Number of records returned in this response.
            - page_number (int): Page number of the current response.
            - records (list): A list of paginated health intraday heart rate records.

    Raises:
        HTTPException: If authentication fails, authorization is denied, or pagination
                       parameters are invalid.
    """
    # Get the total count and paginated records from the database
    total = health_intraday_heart_rate_crud.get_health_intraday_heart_rate_number(token_user_id, db)
    records = health_intraday_heart_rate_crud.get_health_intraday_heart_rate_with_pagination(
        token_user_id, db, page_number, num_records
    )

    # Pydantic will convert ORM models to HealthStepsRead via from_attributes=True
    return health_intraday_heart_rate_schema.HealthIntradayHeartrateListResponse(
        total=total,
        num_records=num_records,
        page_number=page_number,
        records=records,  # type: ignore[arg-type]
    )


@router.post(
    "",
    response_model=health_intraday_heart_rate_schema.HealthIntradayHeartrateRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_health_intraday_heart_rate(
    health_intraday_heart_rate: health_intraday_heart_rate_schema.HealthIntradayHeartrateCreate,
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
) -> health_intraday_heart_rate_schema.HealthIntradayHeartrateRead:
    """
    Create or update health intraday heart rate data for a user.

    This endpoint creates new health intraday heart rate data or updates existing data if an entry
    for the specified timestamp already exists. The operation is determined automatically
    based on whether heart rate data exists for the given timestamp.

    Args:
        health_intraday_heart_rate (health_intraday_heart_rate_schema.HealthIntradayHeartrate): The health intraday heart rate data to create
            or update, including the date and heart rate measuremnt.
        _check_scopes (Callable): Security dependency that verifies the user has
            'health:write' scope.
        token_user_id (int): The ID of the authenticated user extracted from the
            access token.
        db (Session): Database session dependency for database operations.

    Returns:
        health_intraday_heart_rate_schema.HealthIntradayHeartrate: The created or updated health intraday heart rate data.

    Raises:
        HTTPException: 400 error if the date field is not provided in the request.
    """
    if not health_intraday_heart_rate.timestamp:
        raise HTTPException(status_code=400, detail="Date field is required.")

    # Convert date to string format for CRUD function
    timestamp_str = health_intraday_heart_rate.timestamp.isoformat()

    # Check if health_intraday_heart_rate for this date already exists
    heart_rate_for_timestamp = health_intraday_heart_rate_crud.get_health_intraday_heart_rate_by_timerange(
        token_user_id, timestamp_str, timestamp_str, db
    )

    if heart_rate_for_timestamp:
        # Convert to update schema with the existing ID and user_id
        health_intraday_heart_rate_update = health_intraday_heart_rate_schema.HealthIntradayHeartrateUpdate(
            id=heart_rate_for_timestamp[0].id, user_id=token_user_id, **health_intraday_heart_rate.model_dump()
        )
        # Updates the health_intraday_heart_rate in the database and returns it
        return health_intraday_heart_rate_crud.edit_health_intraday_heart_rate(
            token_user_id, health_intraday_heart_rate_update, db
        )
    else:
        # Creates the health_intraday_heart_rate in the database and returns it
        return health_intraday_heart_rate_crud.create_health_intraday_heart_rate(token_user_id, health_intraday_heart_rate, db)


@router.put(
    "",
    response_model=health_intraday_heart_rate_schema.HealthIntradayHeartrateRead,
    status_code=status.HTTP_200_OK,
)
async def edit_health_intraday_heart_rate(
    health_intraday_heart_rate: health_intraday_heart_rate_schema.HealthIntradayHeartrateUpdate,
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
) -> health_intraday_heart_rate_schema.HealthIntradayHeartrateRead:
    """
    Edit health intraday heart rate data for a user.

    This endpoint updates existing health intraday heart rate records in the database for the authenticated user.
    Requires 'health:write' scope for authorization.

    Args:
        health_intraday_heart_rate (health_intraday_heart_rate_schema.HealthIntradayHeartrate): The health intraday heart rate data to be updated,
            containing the new values for the health intraday heart rate record.
        _check_scopes (Callable): Security dependency that verifies the user has 'health:write'
            scope permission.
        token_user_id (int): The user ID extracted from the JWT access token, used to identify
            the user making the request.
        db (Session): Database session dependency for performing database operations.

    Returns:
        health_intraday_heart_rate_schema.HealthIntradayHeartrate: The updated health intraday heart rate record with the new values
            as stored in the database.

    Raises:
        HTTPException: May raise various HTTP exceptions if authorization fails, user is not
            found, or database operations fail.
    """
    # Updates the health_intraday_heart_rate in the database and returns it
    return health_intraday_heart_rate_crud.edit_health_intraday_heart_rate(token_user_id, health_intraday_heart_rate, db)


@router.delete(
    "/{health_intraday_heart_rate_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT
)
async def delete_health_intraday_heart_rate(
    health_intraday_heart_rate_id: int,
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
    Delete a health intraday heart rate record for the authenticated user.

    This endpoint removes a specific health intraday heart rate entry from the database for the user
    identified by the access token. The user must have 'health:write' scope permission.

    Args:
        health_intraday_heart_rate_id (int): The unique identifier of the health intraday heart rate record to delete.
        _check_scopes (Callable): Security dependency that verifies the user has 'health:write' scope.
        token_user_id (int): The user ID extracted from the access token.
        db (Session): Database session dependency for executing the delete operation.

    Returns:
        None: This function does not return a value.

    Raises:
        HTTPException: May be raised by dependencies if:
            - The access token is invalid or expired
            - The user lacks required 'health:write' scope
            - The health intraday heart rate record doesn't exist or doesn't belong to the user
    """
    # Deletes entry from database
    health_intraday_heart_rate_crud.delete_health_intraday_heart_rate(token_user_id, health_intraday_heart_rate_id, db)
