"""Router for weekly streak endpoints."""

from fastapi import APIRouter, Security

import core.dependencies as core_dependencies
import modules.auth.dependencies as auth_dependencies
import modules.users.users_streaks.schema as streak_schema
import modules.users.users_streaks.service as streak_service

router = APIRouter()


@router.get(
    "",
    response_model=streak_schema.WeeklyStreakResponse,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def read_my_weekly_streak(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> streak_schema.WeeklyStreakResponse:
    """Read the authenticated user's weekly streak."""
    return streak_service.read_own_weekly_streak(token_user_id, db)


@router.get(
    "/user/{user_id}",
    response_model=streak_schema.WeeklyStreakResponse | None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def read_user_weekly_streak(
    user_id: core_dependencies.UuidId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> streak_schema.WeeklyStreakResponse | None:
    """Read a user's weekly streak for their profile page.

    The streak is returned to the owner, or to another user when the owner enabled "show on profile" in their
    streak settings. Otherwise the response is ``null``, so the profile hides the streak card.
    """
    return streak_service.read_profile_weekly_streak(user_id, token_user_id, db)
