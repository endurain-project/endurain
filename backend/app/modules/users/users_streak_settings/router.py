"""User weekly streak settings API endpoints."""

from fastapi import APIRouter, Request, Security

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.users.users_streak_settings.schema as streak_settings_schema
import modules.users.users_streak_settings.service as streak_settings_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=streak_settings_schema.UsersStreakSettingsRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"])],
)
def read_streak_settings(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> streak_settings_schema.UsersStreakSettingsRead:
    """Read the authenticated user's weekly streak settings, or the defaults when never saved."""
    return streak_settings_service.get_settings(token_user_id, db)


@router.put(
    "",
    response_model=streak_settings_schema.UsersStreakSettingsRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def update_streak_settings(
    request: Request,
    settings: streak_settings_schema.UsersStreakSettingsUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> streak_settings_schema.UsersStreakSettingsRead:
    """Create or replace the authenticated user's streak settings; an omitted field resets to its default."""
    return streak_settings_service.update_settings(token_user_id, settings, db)
