import os
from datetime import date as datetime_date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import modules.auth.identity_service as auth_identity_service

from fastapi import HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

import core.config as core_config
import core.file_uploads as core_file_uploads
import core.timezone as core_timezone
import modules.health.health_targets.crud as health_targets_crud
import modules.users.users.crud as users_crud
import modules.users.users.schema as users_schema
import modules.users.users_default_gear.crud as user_default_gear_crud
import modules.users.users_integrations.crud as user_integrations_crud
import modules.users.users_privacy_settings.crud as users_privacy_settings_crud


def get_user_by_id_or_404(user_id: int, db: Session) -> users_schema.UsersRead:
    """
    Retrieve user by ID or raise 404 error.

    Args:
        user_id: User ID to search for.
        db: SQLAlchemy database session.

    Returns:
        Users schema (guaranteed non-None).

    Raises:
        HTTPException: 404 if user not found.
    """
    # Get the user from the database
    db_user: users_schema.UsersRead | None = users_crud.get_user_by_id(user_id, db)

    if db_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return db_user


def get_admin_users_or_404(db: Session) -> list[users_schema.UsersRead]:
    """
    Retrieve all admin users from database or raise 404 error.

    Args:
        db: SQLAlchemy database session.

    Returns:
        List of all admin User schemas.

    Raises:
        HTTPException: 404 if no admin users found.
    """
    admins: list[users_schema.UsersRead] = users_crud.get_users_admin(db)

    if not admins:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No admin users found",
        )

    return admins


def check_user_is_active(
    user: users_schema.UsersRead,
) -> None:
    """
    Check if user is active and raise 403 if inactive.

    Args:
        user: User object to check (UsersRead schema).

    Returns:
        None

    Raises:
        HTTPException: 403 if user is not active.
    """
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_user_default_data(
    user_id: int,
    identity_service: "auth_identity_service.IdentityService",
    db: Session,
) -> None:
    """
    Create default data for newly created user.

    Args:
        user_id: ID of user to create default data for.
        identity_service: Identity service used to initialise the
            auth-owned MFA row through the auth boundary.
        db: SQLAlchemy database session.

    Returns:
        None
    """
    # Create the user integrations in the database
    user_integrations_crud.create_user_integrations(user_id, db)

    # Create the user privacy settings
    users_privacy_settings_crud.create_user_privacy_settings(user_id, db)

    # Create the user health targets
    health_targets_crud.create_health_targets(user_id, db)

    # Create the user default gear
    user_default_gear_crud.create_user_default_gear(user_id, db)

    # Create the user's MFA row (disabled by default) via the auth boundary.
    identity_service.initialize_user_mfa(user_id)


_ALLOWED_USER_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".webp"})


async def save_user_image_file(user_id: int, file: UploadFile, db: Session) -> str:
    """
    Save user image file with security validation and update DB.

    Uses centralized file upload handler for validation and async
    I/O, then updates user photo path in database.

    Args:
        user_id: ID of user whose image is being saved.
        file: Uploaded image file (UploadFile).
        db: SQLAlchemy database session.

    Returns:
        Path to saved image file.

    Raises:
        HTTPException: 400 if filename or extension is invalid,
            413 if too large, 500 if upload fails.
    """
    # Validate the user exists off the event loop (blocking sync DB read).
    # A missing user raises HTTPException 404 inside the thread, which
    # propagates through the await unchanged.
    await run_in_threadpool(get_user_by_id_or_404, user_id, db)

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # Defense-in-depth allow-list on the user-supplied extension.
    # SafeUploads still validates the magic number afterwards, so a
    # mismatched signature is rejected even if the extension passes.
    _, file_extension = os.path.splitext(file.filename)
    file_extension = file_extension.lower()
    if file_extension not in _ALLOWED_USER_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported user image file type",
        )

    filename: str = f"{user_id}{file_extension}"

    # Save file using centralized file upload handler
    await core_file_uploads.save_validated_upload(
        file,
        kind=core_file_uploads.UploadKind.IMAGE,
        upload_dir=core_config.USER_IMAGES_DIR,
        filename=filename,
    )

    # Update user photo path in database
    return str(await users_crud.update_user_photo(user_id, db, os.path.join(core_config.USER_IMAGES_DIR, filename)))


async def delete_user_photo_filesystem(user_id: int) -> None:
    """
    Delete user photo files from filesystem.

    Args:
        user_id: ID of user whose photo files to delete.

    Returns:
        None
    """
    await core_file_uploads.delete_files_by_pattern(core_config.USER_IMAGES_DIR, f"{user_id}.*")


def resolve_user_timezone(user_id: int, db: Session) -> str:
    """Return the athlete's IANA timezone, falling back to the server's.

    ``users.timezone`` is nullable: accounts that predate the setting (and users
    who never opened their profile) have none, in which case the server default
    is the only answer available.

    Args:
        user_id: The user whose timezone to resolve.
        db: Database session.

    Returns:
        An IANA timezone name.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if user is not None and user.timezone:
        return user.timezone
    return core_config.settings.TZ


def user_local_today(user_id: int, db: Session) -> datetime_date:
    """Return today's calendar date in the athlete's own timezone.

    Everything that answers "what did I do *today*?" — the health dashboard,
    streaks, interval windows, goal periods — must use this rather than
    ``date.today()`` (the container's zone) or ``datetime.now(UTC).date()``.
    Both of those put an athlete in UTC+13 a day behind for 13 hours out of
    every 24, and one in UTC-11 a day ahead for 11.

    Args:
        user_id: The user whose "today" to resolve.
        db: Database session.

    Returns:
        The user's current calendar date.
    """
    return core_timezone.today_in(resolve_user_timezone(user_id, db))
