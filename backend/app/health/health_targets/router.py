from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security, status
from sqlalchemy.orm import Session

import health.health_targets.schema as health_targets_schema
import health.health_targets.crud as health_targets_crud

import auth.security as auth_security

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get(
    "/",
    response_model=health_targets_schema.HealthTargetsRead | None,
)
async def read_health_targets_all(
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
) -> health_targets_schema.HealthTargetsRead | None:
    """
    Retrieve all health targets for the authenticated user.

    This endpoint fetches all health targets associated with the user identified by the
    access token. It requires the 'health:read' scope for authorization.

    Args:
        _check_scopes (Callable): Security dependency that verifies the user has the
            required 'health:read' scope. The underscore prefix indicates this parameter
            is injected by FastAPI's security system but not directly used in the function.
        token_user_id (int): The user ID extracted from the JWT access token, automatically
            injected by the authentication dependency.
        db (Session): SQLAlchemy database session dependency for executing database queries.

    Returns:
        health_targets_schema.HealthTargetsRead | None: The
            health targets object containing all targets for
            the user, or None if no targets are found.

    Raises:
        HTTPException: May raise 401 Unauthorized if the token is invalid or expired.
        HTTPException: May raise 403 Forbidden if the user lacks the required 'health:read' scope.
    """
    # Get the health_targets from the database
    return health_targets_crud.get_health_targets_by_user_id(token_user_id, db)


@router.put(
    "/",
    response_model=health_targets_schema.HealthTargetsRead,
    status_code=status.HTTP_200_OK,
)
async def update_health_targets(
    health_targets: health_targets_schema.HealthTargetsUpdate,
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
) -> health_targets_schema.HealthTargetsRead:
    """
    Update health targets for the authenticated user.

    This endpoint allows users to modify their health-related targets such as
    weight goals, activity targets, or other health metrics.

    Args:
        health_targets (
            health_targets_schema.HealthTargetsUpdate): The
            health targets data to be updated, containing the
            new values for various health metrics.
        _check_scopes (Callable): Security dependency that
            verifies the user has 'health:write' scope
            permission.
        token_user_id (int): The authenticated user's ID
            extracted from the access token.
        db (Session): Database session dependency for database
            operations.

    Returns:
        health_targets_schema.HealthTargetsRead: The updated
            health targets object reflecting the changes made
            in the database.

    Raises:
        HTTPException: May raise authentication or authorization errors if the user
            lacks proper permissions or if the token is invalid.
        HTTPException: May raise database-related errors if the update operation fails.
    """
    # Update the health_targets in the database
    return health_targets_crud.edit_health_target(health_targets, token_user_id, db)
