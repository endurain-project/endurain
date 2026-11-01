"""User weekly streak settings API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

import core.database as core_database
import modules.auth.dependencies as auth_dependencies
import modules.users.users_streak_settings.crud as streak_settings_crud
import modules.users.users_streak_settings.schema as streak_settings_schema

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=streak_settings_schema.UsersStreakSettingsRead,
    status_code=status.HTTP_200_OK,
)
def read_streak_settings(
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> streak_settings_schema.UsersStreakSettingsRead:
    """
    Read the authenticated user's weekly streak settings.

    Args:
        token_user_id: User ID from access token.
        db: Database session dependency.

    Returns:
        The stored settings, or defaults when never saved.
    """
    return streak_settings_crud.get_streak_settings_by_user_id(token_user_id, db)


@router.put(
    "",
    response_model=streak_settings_schema.UsersStreakSettingsRead,
    status_code=status.HTTP_200_OK,
)
def update_streak_settings(
    settings: streak_settings_schema.UsersStreakSettingsUpdate,
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> streak_settings_schema.UsersStreakSettingsRead:
    """
    Create or replace the authenticated user's streak settings.

    Args:
        settings: New settings values.
        token_user_id: User ID from access token.
        db: Database session dependency.

    Returns:
        The stored settings.
    """
    return streak_settings_crud.upsert_streak_settings(token_user_id, settings, db)
