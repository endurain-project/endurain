"""CRUD operations for user weekly streak settings."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.users.users_streak_settings.models as streak_settings_models
import modules.users.users_streak_settings.schema as streak_settings_schema

# Private internal helpers


def _transform(
    settings: streak_settings_models.UsersStreakSettings,
) -> streak_settings_schema.UsersStreakSettingsRead:
    """
    Transform a streak settings ORM instance to a Pydantic schema.

    Args:
        settings: The streak settings ORM instance.

    Returns:
        The streak settings as a read schema.
    """
    return streak_settings_schema.UsersStreakSettingsRead.model_validate(settings)


def _get_model_by_user_id(user_id: int, db: Session) -> streak_settings_models.UsersStreakSettings | None:
    """
    Fetch the streak settings ORM row for a user.

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


def _default_settings(user_id: int) -> streak_settings_schema.UsersStreakSettingsRead:
    """
    Build the default settings for a user without a stored row.

    Args:
        user_id: Owner of the settings.

    Returns:
        Read schema populated with defaults.
    """
    return streak_settings_schema.UsersStreakSettingsRead(user_id=user_id)


# Public CRUD functions


@core_decorators.handle_db_errors
def get_streak_settings_by_user_id(user_id: int, db: Session) -> streak_settings_schema.UsersStreakSettingsRead:
    """
    Retrieve streak settings for a user, falling back to defaults.

    No row is created on read; defaults are returned until the
    user saves their settings for the first time.

    Args:
        user_id: Owner of the settings.
        db: SQLAlchemy database session.

    Returns:
        The stored settings, or defaults when none exist.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    db_settings = _get_model_by_user_id(user_id, db)
    return _transform(db_settings) if db_settings else _default_settings(user_id)


@core_decorators.handle_db_errors
def upsert_streak_settings(
    user_id: int,
    settings: streak_settings_schema.UsersStreakSettingsUpdate,
    db: Session,
) -> streak_settings_schema.UsersStreakSettingsRead:
    """
    Create or replace streak settings for a user.

    Args:
        user_id: Owner of the settings.
        settings: New settings values.
        db: SQLAlchemy database session.

    Returns:
        The stored settings.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    db_settings = _get_model_by_user_id(user_id, db)
    if db_settings is None:
        db_settings = streak_settings_models.UsersStreakSettings(user_id=user_id)
        db.add(db_settings)

    db_settings.min_activities_per_week = settings.min_activities_per_week
    db_settings.activity_types = settings.activity_types
    db_settings.show_on_profile = settings.show_on_profile

    try:
        db.commit()
    except IntegrityError:
        # A concurrent request created the row first: retry as an update.
        db.rollback()
        db_settings = _get_model_by_user_id(user_id, db)
        if db_settings is None:
            raise
        db_settings.min_activities_per_week = settings.min_activities_per_week
        db_settings.activity_types = settings.activity_types
        db_settings.show_on_profile = settings.show_on_profile
        db.commit()

    db.refresh(db_settings)
    return _transform(db_settings)
