from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import health_sleep.schema as health_sleep_schema
import health_sleep.crud as health_sleep_crud

import auth.security as auth_security

import core.database as core_database
import core.dependencies as core_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=health_sleep_schema.HealthSleepListResponse,
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

    return health_sleep_schema.HealthSleepListResponse(total=total, records=records)


@router.get(
    "/page_number/{page_number}/num_records/{num_records}",
    response_model=health_sleep_schema.HealthSleepListResponse,
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

    return health_sleep_schema.HealthSleepListResponse(total=total, records=records)


@router.delete("/{health_sleep_id}", status_code=204)
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
            - The health steps record doesn't exist or doesn't belong to the user
    """
    # Deletes entry from database
    health_sleep_crud.delete_health_sleep(token_user_id, health_sleep_id, db)
