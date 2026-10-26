"""User default gear API endpoints."""

from fastapi import APIRouter, Request, Response, Security, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.users.users_default_gear.schema as user_default_gear_schema
import modules.users.users_default_gear.service as user_default_gear_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=user_default_gear_schema.UsersDefaultGearRead,
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
def read_user_default_gear(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> user_default_gear_schema.UsersDefaultGearRead | None:
    """Retrieve default gear settings for authenticated user.

    Args:
        token_user_id: User ID from access token.
        db: Database session dependency.
        response: The response, which carries the settings' ETag.

    Returns:
        User default gear settings.
    """
    default_gear = user_default_gear_service.get_default_gear(token_user_id, db)
    if default_gear is not None:
        response.headers["ETag"] = core_etag.format_etag(default_gear.version)
    return default_gear


@router.patch(
    "",
    response_model=user_default_gear_schema.UsersDefaultGearRead,
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_user_default_gear(
    request: Request,
    user_default_gear: user_default_gear_schema.UsersDefaultGearUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> user_default_gear_schema.UsersDefaultGearRead:
    """Update default gear settings for authenticated user.

    Args:
        request: The incoming request, read by the rate limiter.
        user_default_gear: Updated gear settings.
        token_user_id: User ID from access token.
        db: Database session dependency.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition.

    Returns:
        Updated user default gear settings.
    """
    updated = user_default_gear_service.edit_default_gear(user_default_gear, token_user_id, db, if_match=if_match)
    response.headers["ETag"] = core_etag.format_etag(updated.version)
    return updated
