"""FastAPI router for health targets endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.health_targets.schema as health_targets_schema
import modules.health.health_targets.service as health_targets_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=health_targets_schema.HealthTargetsRead | None,
    status_code=status.HTTP_200_OK,
)
def read_health_targets_all(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_targets_schema.HealthTargetsRead | None:
    """Retrieve all health targets for the authenticated user.

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
    return health_targets_service.get_health_targets(token_user_id, db)


@router.put(
    "",
    response_model=health_targets_schema.HealthTargetsRead,
    status_code=status.HTTP_200_OK,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def update_health_targets(
    request: Request,
    health_targets: health_targets_schema.HealthTargetsUpdate,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> health_targets_schema.HealthTargetsRead:
    """Update health targets for the authenticated user.

    This endpoint allows users to modify their health-related targets such as
    weight goals, activity targets, or other health metrics.

    Args:
        request: The incoming request, read by the rate limiter.
        health_targets: The health targets to update, containing the new values for
            the health metrics.
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
    return health_targets_service.update_health_targets(health_targets, token_user_id, db)
