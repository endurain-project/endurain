"""The streak settings surface consumed by other packages (the weekly streak)."""

import uuid

from sqlalchemy.orm import Session

import modules.users.users_streak_settings.crud as streak_settings_crud
import modules.users.users_streak_settings.schema as streak_settings_schema


def get_streak_settings(user_id: uuid.UUID, db: Session) -> streak_settings_schema.UsersStreakSettingsRead:
    """Return a user's streak settings, or the defaults when never saved.

    Args:
        user_id: Owner of the settings.
        db: Database session.

    Returns:
        The stored settings, or defaults.
    """
    return streak_settings_crud.get_streak_settings_by_user_id(user_id, db)
