"""User weekly streak settings service: owns the settings transaction."""

import uuid

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.users.users_streak_settings.crud as streak_settings_crud
import modules.users.users_streak_settings.schema as streak_settings_schema

logger = core_logger.get_logger(__name__)


def get_settings(user_id: uuid.UUID, db: Session) -> streak_settings_schema.UsersStreakSettingsRead:
    """Read a user's streak settings, or the defaults when never saved.

    Args:
        user_id: Owner of the settings.
        db: Database session.

    Returns:
        The stored settings, or defaults.
    """
    return streak_settings_crud.get_streak_settings_by_user_id(user_id, db)


def update_settings(
    user_id: uuid.UUID,
    settings: streak_settings_schema.UsersStreakSettingsUpdate,
    db: Session,
) -> streak_settings_schema.UsersStreakSettingsRead:
    """Create or replace a user's streak settings and commit.

    Args:
        user_id: Owner of the settings.
        settings: New settings values.
        db: Database session.

    Returns:
        The stored settings.
    """
    stored = streak_settings_crud.stage_streak_settings(user_id, settings, db)
    db.commit()
    logger.info("User streak settings updated", extra=core_logger.context(user_id=user_id))
    return stored
