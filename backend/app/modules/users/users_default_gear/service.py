"""Application logic for user default gear.

Decides who may edit which settings and which gears they may point at, and owns the
commit for the user's own requests. What other modules may consume lives in
:mod:`modules.users.users_default_gear.integration_service`.
"""

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.logger as core_logger
import modules.gears.gear.constants as gears_constants
import modules.gears.gear.integration_service as gears_integration
import modules.users.users_default_gear.constants as users_default_gear_constants
import modules.users.users_default_gear.crud as users_default_gear_crud
import modules.users.users_default_gear.schema as users_default_gear_schema

logger = core_logger.get_logger(__name__)


def get_default_gear(user_id: int, db: Session) -> users_default_gear_schema.UsersDefaultGearRead | None:
    """Return a user's default gear settings.

    Args:
        user_id: The user to read settings for.
        db: Database session.

    Returns:
        The default gear settings, or None if the user has none.
    """
    return users_default_gear_crud.get_user_default_gear_by_user_id(user_id, db)


def stage_default_gear_edit(
    user_default_gear: users_default_gear_schema.UsersDefaultGearUpdate,
    user_id: int,
    db: Session,
    *,
    if_match: str,
) -> users_default_gear_schema.UsersDefaultGearRead:
    """Stage an update of a user's default gear after checking the edit is allowed.

    Args:
        user_default_gear: The fields to change.
        user_id: The user whose settings are edited.
        db: Database session.
        if_match: The ``If-Match`` precondition, or ``*`` to overwrite.

    Returns:
        The updated default gear settings.

    Raises:
        NotFoundError: If a gear is not the user's, or the user has no settings.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    changes = user_default_gear.model_dump(exclude_unset=True)
    gears_integration.require_owned_gears(user_id, changes.values(), db)

    return users_default_gear_crud.edit_user_default_gear(user_default_gear, user_id, db, if_match=if_match)


def restore_profile_default_gear(
    record: dict[str, Any], ids: dict[str, dict[int, int]], user_id: int, db: Session
) -> bool:
    """Stage the default gear of a profile archive, moved onto the restored gears; the caller commits.

    Args:
        record: The archived default gear settings.
        ids: The ids restored so far; the archived-to-stored gear ids are read from ``"gears"``.
        user_id: The importing user.
        db: Database session.

    Returns:
        True when the settings were staged; False when the archive's were invalid.
    """
    if users_default_gear_crud.get_user_default_gear_by_user_id(user_id, db) is None:
        logger.debug("No existing user default gear, creating new record")
        users_default_gear_crud.create_user_default_gear(user_id, db)

    # The archive's record and owner are the exporting account's; the update names neither.
    settings = {key: value for key, value in record.items() if key not in ("id", "user_id", "version")}
    gears_id_mapping = ids.get(gears_constants.PROFILE_ARCHIVE_KEY, {})
    for field in set(users_default_gear_constants.ACTIVITY_TYPE_TO_GEAR_ATTR.values()):
        old_gear_id = settings.get(field)
        settings[field] = gears_id_mapping.get(old_gear_id) if old_gear_id is not None else None

    try:
        update = users_default_gear_schema.UsersDefaultGearUpdate(**settings)
    except ValidationError:
        logger.warning("Skipped invalid user default gear")
        return False
    stage_default_gear_edit(update, user_id, db, if_match="*")
    logger.debug("Imported user default gear")
    return True


def edit_default_gear(
    user_default_gear: users_default_gear_schema.UsersDefaultGearUpdate,
    user_id: int,
    db: Session,
    *,
    if_match: str,
) -> users_default_gear_schema.UsersDefaultGearRead:
    """Update a user's default gear settings and commit.

    Args:
        user_default_gear: The fields to change.
        user_id: The user whose settings are edited.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated default gear settings.

    Raises:
        NotFoundError: If a gear is not the user's, or the user has no settings.
        PreconditionFailedError: If the settings changed since the client read them.
    """
    with core_etag.refuse_stale_write(
        db,
        "default gear",
        lambda: users_default_gear_crud.get_user_default_gear_by_user_id(user_id, db) is not None,
        "User default gear not found",
    ):
        updated = stage_default_gear_edit(user_default_gear, user_id, db, if_match=if_match)
        db.commit()
    logger.debug("Default gear updated", extra=core_logger.context(user_id=user_id))
    return updated
