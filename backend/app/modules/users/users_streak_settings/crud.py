"""CRUD operations for user weekly streak settings."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import modules.users.users_streak_settings.models as streak_settings_models
import modules.users.users_streak_settings.schema as streak_settings_schema


def _get_model_by_user_id(user_id: uuid.UUID, db: Session) -> streak_settings_models.UsersStreakSettings | None:
    """Fetch the streak settings ORM row for a user.

    Args:
        user_id: Owner of the settings.
        db: SQLAlchemy database session.

    Returns:
        The ORM row, or None when the user has no row yet.
    """
    stmt = select(streak_settings_models.UsersStreakSettings).where(
        streak_settings_models.UsersStreakSettings.user_id == user_id
    )
    return db.execute(stmt).scalar_one_or_none()


def _apply(
    db_settings: streak_settings_models.UsersStreakSettings,
    settings: streak_settings_schema.UsersStreakSettingsUpdate,
) -> None:
    """Copy the new settings values onto an ORM row.

    Args:
        db_settings: The row to update.
        settings: New settings values.
    """
    db_settings.min_activities_per_week = settings.min_activities_per_week
    db_settings.activity_types = settings.activity_types
    db_settings.show_on_profile = settings.show_on_profile


def get_streak_settings_by_user_id(user_id: uuid.UUID, db: Session) -> streak_settings_schema.UsersStreakSettingsRead:
    """Retrieve streak settings for a user, falling back to defaults.

    No row is created on read; defaults are returned until the
    user saves their settings for the first time.

    Args:
        user_id: Owner of the settings.
        db: SQLAlchemy database session.

    Returns:
        The stored settings, or defaults when none exist.
    """
    db_settings = _get_model_by_user_id(user_id, db)
    if db_settings is None:
        return streak_settings_schema.UsersStreakSettingsRead(user_id=user_id)
    return streak_settings_schema.UsersStreakSettingsRead.model_validate(db_settings)


def stage_streak_settings(
    user_id: uuid.UUID,
    settings: streak_settings_schema.UsersStreakSettingsUpdate,
    db: Session,
) -> streak_settings_schema.UsersStreakSettingsRead:
    """Stage a create or replace of a user's streak settings (flushed, not committed).

    Args:
        user_id: Owner of the settings.
        settings: New settings values.
        db: SQLAlchemy database session.

    Returns:
        The staged settings.
    """
    db_settings = _get_model_by_user_id(user_id, db)
    if db_settings is None:
        try:
            # A savepoint, so a concurrent first save only rolls back this insert.
            with db.begin_nested():
                db_settings = streak_settings_models.UsersStreakSettings(user_id=user_id)
                _apply(db_settings, settings)
                db.add(db_settings)
        except IntegrityError:
            # Another request created the row first: update it instead.
            db_settings = _get_model_by_user_id(user_id, db)
            if db_settings is None:
                raise
            _apply(db_settings, settings)
            db.flush()
    else:
        _apply(db_settings, settings)
        db.flush()

    db.refresh(db_settings)
    return streak_settings_schema.UsersStreakSettingsRead.model_validate(db_settings)
