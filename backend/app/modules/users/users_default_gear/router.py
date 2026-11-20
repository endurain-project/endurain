"""User default gear API endpoints."""

from fastapi import APIRouter, Request, Response, Security

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
    response_model=user_default_gear_schema.UserDefaultGearRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"])],
)
def read_user_default_gear(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> user_default_gear_schema.UserDefaultGearRead | None:
    """Retrieve default gear settings for authenticated user."""
    default_gear = user_default_gear_service.get_default_gear(token_user_id, db)
    if default_gear is not None:
        core_etag.set_etag(response, default_gear.version)
    return default_gear


@router.patch(
    "",
    response_model=user_default_gear_schema.UserDefaultGearRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_user_default_gear(
    request: Request,
    user_default_gear: user_default_gear_schema.UserDefaultGearUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> user_default_gear_schema.UserDefaultGearRead:
    """Update default gear settings for authenticated user."""
    updated = user_default_gear_service.edit_default_gear(user_default_gear, token_user_id, db, if_match=if_match)
    core_etag.set_etag(response, updated.version)
    return updated
