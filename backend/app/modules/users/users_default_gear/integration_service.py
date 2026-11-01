"""The user default gear surface other modules may call.

Writes stage; the caller owns the commit.
"""

from sqlalchemy.orm import Session

import modules.users.users_default_gear.constants as users_default_gear_constants
import modules.users.users_default_gear.crud as users_default_gear_crud
import modules.users.users_default_gear.schema as users_default_gear_schema
import modules.users.users_default_gear.service as users_default_gear_service


def get_default_gear(user_id: int, db: Session) -> users_default_gear_schema.UsersDefaultGearRead | None:
    """Return a user's default gear settings.

    Args:
        user_id: The user to read settings for.
        db: Database session.

    Returns:
        The default gear settings, or None if the user has none.
    """
    return users_default_gear_crud.get_user_default_gear_by_user_id(user_id, db)


def get_default_gear_for_activity_type(user_id: int, activity_type: int, db: Session) -> int | None:
    """Return the user's default gear id for an activity type, if they set one.

    Args:
        user_id: The owning user.
        activity_type: The numeric sport type.
        db: Database session.

    Returns:
        The gear id, or None when the user has no default for this type.
    """
    default_gear = users_default_gear_crud.get_user_default_gear_by_user_id(user_id, db)
    attr_name = users_default_gear_constants.ACTIVITY_TYPE_TO_GEAR_ATTR.get(activity_type)
    if default_gear is None or attr_name is None:
        return None

    return getattr(default_gear, attr_name, None)


def create_default_gear(user_id: int, db: Session) -> users_default_gear_schema.UsersDefaultGearRead:
    """Stage empty default gear settings for a new user.

    Args:
        user_id: The user to create settings for.
        db: Database session.

    Returns:
        The created default gear settings.

    Raises:
        ConflictError: If the user already has default gear settings.
    """
    return users_default_gear_crud.create_user_default_gear(user_id, db)


def edit_default_gear(
    user_default_gear: users_default_gear_schema.UsersDefaultGearUpdate,
    user_id: int,
    db: Session,
    *,
    if_match: str,
) -> users_default_gear_schema.UsersDefaultGearRead:
    """Stage an update of a user's default gear settings.

    Args:
        user_default_gear: The fields to change.
        user_id: The user whose settings are edited.
        db: Database session.
        if_match: The ``If-Match`` precondition, or ``*`` to overwrite (the profile importer).

    Returns:
        The updated default gear settings.

    Raises:
        NotFoundError: If a gear is not the user's, or the user has no settings.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    return users_default_gear_service.stage_default_gear_edit(user_default_gear, user_id, db, if_match=if_match)
