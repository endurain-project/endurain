"""Router for weekly streak endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import core.database as core_database
import core.timezone as core_timezone
import modules.auth.dependencies as auth_dependencies
import modules.users.users.dependencies as users_dependencies
import modules.users.users.utils as users_utils
import modules.users.users_streak_settings.crud as streak_settings_crud
import modules.users.users_streaks.schema as streak_schema
import modules.users.users_streaks.service as streak_service

router = APIRouter()


def _streak_for_user(user_id: int, db: Session, *, user_is_owner: bool) -> streak_schema.WeeklyStreakResponse:
    """
    Load settings and calculate the streak for a user.

    Args:
        user_id: Target user ID.
        db: Database session.
        user_is_owner: Whether the requester is the target user.

    Returns:
        The weekly streak response.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    user = users_utils.get_user_by_id_or_404(user_id, db)
    settings = streak_settings_crud.get_streak_settings_by_user_id(user_id, db)
    today = core_timezone.today_in(users_utils.timezone_or_default(user.timezone))
    return streak_service.get_weekly_streak(
        user_id, user.first_day_of_week, settings, today, db, user_is_owner=user_is_owner
    )


@router.get(
    "",
    response_model=streak_schema.WeeklyStreakResponse,
)
async def read_my_weekly_streak(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["activities:read"]),
    ],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> streak_schema.WeeklyStreakResponse:
    """
    Read the authenticated user's weekly streak.

    Args:
        _check_scopes: Dependency that checks required scopes.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        The weekly streak response.
    """
    return _streak_for_user(token_user_id, db, user_is_owner=True)


@router.get(
    "/user/{user_id}",
    response_model=streak_schema.WeeklyStreakResponse | None,
)
async def read_user_weekly_streak(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["activities:read"]),
    ],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> streak_schema.WeeklyStreakResponse | None:
    """
    Read another user's weekly streak for their profile page.

    The streak is only returned when the profile owner enabled
    "show on profile" in their streak settings, or when the
    viewer is the owner. Otherwise ``null`` is returned so the
    profile simply hides the streak card.

    Args:
        user_id: Profile owner's user ID.
        _validate_id: User ID validation dependency.
        _check_scopes: Dependency that checks required scopes.
        token_user_id: Authenticated viewer's user ID.
        db: Database session.

    Returns:
        The weekly streak response, or None if not shared.
    """
    user_is_owner = user_id == token_user_id
    if not user_is_owner:
        settings = streak_settings_crud.get_streak_settings_by_user_id(user_id, db)
        if not settings.show_on_profile:
            return None
    return _streak_for_user(user_id, db, user_is_owner=user_is_owner)
