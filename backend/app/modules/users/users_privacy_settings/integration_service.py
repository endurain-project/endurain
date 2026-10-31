"""The user privacy settings surface other modules may call.

Writes stage; the caller owns the commit.
"""

from sqlalchemy.orm import Session

import modules.users.users_privacy_settings.constants as users_privacy_settings_constants
import modules.users.users_privacy_settings.crud as users_privacy_settings_crud
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema


def get_privacy_settings(user_id: int, db: Session) -> users_privacy_settings_schema.UsersPrivacySettingsRead | None:
    """Return a user's privacy settings.

    Args:
        user_id: The user to read settings for.
        db: Database session.

    Returns:
        The privacy settings, or None if the user has none.
    """
    return users_privacy_settings_crud.get_user_privacy_settings_by_user_id(user_id, db)


def create_privacy_settings(user_id: int, db: Session) -> users_privacy_settings_schema.UsersPrivacySettingsRead:
    """Stage default privacy settings for a new user.

    Args:
        user_id: The user to create settings for.
        db: Database session.

    Returns:
        The created privacy settings.

    Raises:
        ConflictError: If the user already has privacy settings.
    """
    return users_privacy_settings_crud.create_user_privacy_settings(user_id, db)


def edit_privacy_settings(
    user_id: int,
    privacy_settings: users_privacy_settings_schema.UsersPrivacySettingsUpdate,
    db: Session,
    *,
    if_match: str,
) -> users_privacy_settings_schema.UsersPrivacySettingsRead:
    """Stage an update of a user's privacy settings.

    Args:
        user_id: The user whose settings to update.
        privacy_settings: The fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition, or ``*`` to overwrite.

    Returns:
        The updated privacy settings.

    Raises:
        NotFoundError: If the user has no privacy settings.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    # The caller composes this into its own unit of work (the profile edit, the importer) and decides the
    # precondition: the profile edit names the version its client read, the importer overwrites.
    return users_privacy_settings_crud.edit_user_privacy_settings(user_id, privacy_settings, db, if_match=if_match)


def visibility_to_int(
    visibility: str | users_privacy_settings_schema.ActivityVisibility | None,
) -> int:
    """Convert a visibility string or enum to the integer activities store.

    Args:
        visibility: Visibility as string, enum, or None.

    Returns:
        Integer representation (0=public, 1=followers, 2=private). An unset or unrecognized
        value resolves to private, never to public.
    """
    value = visibility.value if isinstance(visibility, users_privacy_settings_schema.ActivityVisibility) else visibility
    return users_privacy_settings_constants.VISIBILITY_LEVELS.get(
        value, users_privacy_settings_constants.FALLBACK_VISIBILITY_LEVEL
    )
