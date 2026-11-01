"""The users operations exposed only to data migrations."""

from sqlalchemy.orm import Session

import modules.users.users.constants as users_constants
import modules.users.users.crud as users_crud
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

USER_IMAGE_STORAGE_AREA = users_constants.USER_IMAGE_STORAGE_AREA


def list_users(db: Session) -> list[users_schema.UsersRead]:
    """Return every user.

    Args:
        db: Database session.

    Returns:
        All user schemas.
    """
    return users_crud.get_all_users(db)


def get_stored_photo_keys(db: Session) -> list[tuple[int, str | None]]:
    """Return every user's raw stored photo value.

    The read schema resolves ``photo_path`` into a signed URL, so a migration that needs the
    value actually on the row cannot go through :func:`list_users`.

    Args:
        db: Database session.

    Returns:
        ``(user_id, photo_path)`` pairs.
    """
    return users_crud.get_stored_photo_keys(db)


def set_photo_key(user_id: int, photo_key: str | None, db: Session) -> None:
    """Set a user's stored photo key and commit.

    Args:
        user_id: The user to update.
        photo_key: The ``StorageProvider`` key, or ``None`` to clear the photo.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
    """
    users_crud.update_user(user_id, {"photo_path": photo_key}, db)
    db.commit()


def edit_user(user_id: int, user: users_schema.UsersEdit, db: Session) -> None:
    """Apply an administrative edit to a user and commit.

    Args:
        user_id: The user to update.
        user: The user data to apply.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
        ConflictError: If the username or email is already taken.
    """
    # A migration overwrites whatever the row holds, so it names no version.
    users_service.stage_user_edit(user_id, user, db, if_match="*")
    db.commit()
