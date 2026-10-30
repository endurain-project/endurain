"""FastAPI router for health targets endpoints."""

from fastapi import APIRouter, Request, Response, Security

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.health_targets.schema as health_targets_schema
import modules.health.health_targets.service as health_targets_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=health_targets_schema.HealthTargetsRead | None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health_targets:read"])],
)
def read_health_targets_all(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> health_targets_schema.HealthTargetsRead | None:
    """Retrieve all health targets for the authenticated user.

    This endpoint fetches all health targets associated with the user identified by the
    access token. It requires the 'health_targets:read' scope for authorization.

    Args:
        token_user_id (int): The user ID extracted from the JWT access token, automatically
            injected by the authentication dependency.
        db (Session): SQLAlchemy database session dependency for executing database queries.
        response: The response, which carries the targets' ETag.

    Returns:
        health_targets_schema.HealthTargetsRead | None: The
            health targets object containing all targets for
            the user, or None if no targets are found.
    """
    targets = health_targets_service.get_health_targets(token_user_id, db)
    if targets is not None:
        core_etag.set_etag(response, targets.version)
    return targets


@router.patch(
    "",
    response_model=health_targets_schema.HealthTargetsRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health_targets:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def update_health_targets(
    request: Request,
    health_targets: health_targets_schema.HealthTargetsUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> health_targets_schema.HealthTargetsRead:
    """Update health targets for the authenticated user.

    This endpoint allows users to modify their health-related targets such as
    weight goals, activity targets, or other health metrics.

    Args:
        request: The incoming request, read by the rate limiter.
        health_targets: The health targets to update, containing the new values for
            the health metrics.
        token_user_id (int): The authenticated user's ID
            extracted from the access token.
        db (Session): Database session dependency for database
            operations.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition.

    Returns:
        health_targets_schema.HealthTargetsRead: The updated
            health targets object reflecting the changes made
            in the database.

    Raises:
        NotFoundError: If the user has no targets.
        PreconditionFailedError: If the targets changed since the client read them.
    """
    updated = health_targets_service.update_health_targets(health_targets, token_user_id, db, if_match=if_match)
    core_etag.set_etag(response, updated.version)
    return updated
