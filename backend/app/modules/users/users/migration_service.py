"""The users operations exposed only to data migrations."""

import uuid

from sqlalchemy.orm import Session

import modules.users.users.constants as users_constants
import modules.users.users.crud as users_crud

USER_IMAGE_STORAGE_AREA = users_constants.USER_IMAGE_STORAGE_AREA
photo_key = users_constants.photo_key
replace_photo_keys = users_crud.replace_photo_keys


def get_stored_photo_keys(db: Session) -> list[tuple[uuid.UUID, str | None]]:
    """Return every user's raw stored photo value.

    The read schema resolves ``photo_path`` into a signed URL, so a migration that needs the
    value actually on the row cannot go through the read schemas.

    Args:
        db: Database session.

    Returns:
        ``(user_id, photo_path)`` pairs.
    """
    return users_crud.get_stored_photo_keys(db)
