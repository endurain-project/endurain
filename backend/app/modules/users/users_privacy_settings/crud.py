"""CRUD operations for user privacy settings."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.users.users_privacy_settings.models as users_privacy_settings_models
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema
import modules.users.users_privacy_settings.serializers as users_privacy_settings_serializers


def get_user_privacy_settings_by_user_id(
    user_id: int, db: Session
) -> users_privacy_settings_schema.UsersPrivacySettingsRead | None:
    """Retrieve privacy settings for a specific user.

    Args:
        user_id: The ID of the user to fetch settings for.
        db: Database session.

    Returns:
        The privacy settings if found, None otherwise.
    """
    stmt = select(users_privacy_settings_models.UsersPrivacySettings).where(
        users_privacy_settings_models.UsersPrivacySettings.user_id == user_id
    )
    db_privacy_settings = db.execute(stmt).scalar_one_or_none()
    return users_privacy_settings_serializers.to_read_schema(db_privacy_settings) if db_privacy_settings else None


def create_user_privacy_settings(user_id: int, db: Session) -> users_privacy_settings_schema.UsersPrivacySettingsRead:
    """Stage privacy settings for a user with the model defaults (flushed, not committed).

    Args:
        user_id: The ID of the user to create settings for.
        db: Database session.

    Returns:
        The created privacy settings.

    Raises:
        ConflictError: If settings already exist for the user.
    """
    db_privacy_settings = users_privacy_settings_models.UsersPrivacySettings(user_id=user_id)
    try:
        db.add(db_privacy_settings)
        db.flush()
        db.refresh(db_privacy_settings)
    except IntegrityError as err:
        raise core_exceptions.ConflictError("Privacy settings already exist for this user") from err

    return users_privacy_settings_serializers.to_read_schema(db_privacy_settings)


def edit_user_privacy_settings(
    user_id: int,
    user_privacy_settings_data: users_privacy_settings_schema.UsersPrivacySettingsUpdate,
    db: Session,
    *,
    if_match: str,
) -> users_privacy_settings_schema.UsersPrivacySettingsRead:
    """Stage an update of a user's privacy settings (flushed, not committed).

    Args:
        user_id: The ID of the user to update settings for.
        user_privacy_settings_data: Schema with fields to update.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated privacy settings.

    Raises:
        NotFoundError: If the user has no privacy settings.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    stmt = select(users_privacy_settings_models.UsersPrivacySettings).where(
        users_privacy_settings_models.UsersPrivacySettings.user_id == user_id
    )
    db_privacy_settings = db.execute(stmt).scalar_one_or_none()
    if db_privacy_settings is None:
        raise core_exceptions.NotFoundError("User privacy settings not found")
    core_etag.require_if_match(if_match, db_privacy_settings.version, "privacy settings")

    changes = user_privacy_settings_data.model_dump(exclude_unset=True, exclude={"user_id", "id"})
    for key, value in changes.items():
        setattr(db_privacy_settings, key, value)

    db.flush()
    db.refresh(db_privacy_settings)

    return users_privacy_settings_serializers.to_read_schema(db_privacy_settings)
