"""CRUD operations for user management."""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from urllib.parse import unquote

import auth.password_hasher as auth_password_hasher

import users.users.schema as users_schema
import users.users.utils as users_utils
import users.users.models as users_models

import health.health_weight.utils as health_weight_utils

import server_settings.utils as server_settings_utils
import server_settings.schema as server_settings_schema

import core.decorators as core_decorators


@core_decorators.handle_db_errors
def get_all_users(db: Session) -> list[users_models.Users]:
    """
    Retrieve all users from the database.

    Args:
        db: SQLAlchemy database session.

    Returns:
        List of all User models.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(users_models.Users)
    return db.execute(stmt).scalars().all()


@core_decorators.handle_db_errors
def get_users_number(db: Session) -> int:
    """
    Get total count of users in the database.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Total number of users.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(func.count(users_models.Users.id))
    return db.execute(stmt).scalar_one()


@core_decorators.handle_db_errors
def get_users_with_pagination(
    db: Session, page_number: int = 1, num_records: int = 5
) -> list[users_models.Users]:
    """
    Retrieve paginated list of users.

    Args:
        db: SQLAlchemy database session.
        page_number: Page number to retrieve (1-indexed).
        num_records: Number of records per page.

    Returns:
        List of User models for the requested page.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = (
        select(users_models.Users)
        .order_by(users_models.Users.username)
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    return db.execute(stmt).scalars().all()


@core_decorators.handle_db_errors
def get_user_by_username(
    username: str, db: Session, contains: bool = False
) -> list[users_models.Users] | users_models.Users | None:
    """
    Retrieve user by username.

    Args:
        username: Username to search for.
        db: SQLAlchemy database session.
        contains: If True, performs partial match search and returns
                  list of matching users. If False, performs exact
                  match and returns single user or None.

    Returns:
        If contains=False: Users model if found, None otherwise.
        If contains=True: List of User models matching the search.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    # Decode and normalize search term (needed for both exact and partial matches)
    normalized_username = unquote(username).replace("+", " ").lower()

    if contains:
        # Escape LIKE special characters to prevent SQL injection
        escaped_username = (
            normalized_username.replace("\\", "\\\\")
            .replace("%", r"\%")
            .replace("_", r"\_")
        )

        # Query users with username containing the search term
        stmt = select(users_models.Users).where(
            func.lower(users_models.Users.username).like(
                f"%{escaped_username}%", escape="\\"
            )
        )
        return db.execute(stmt).scalars().all()
    else:
        # Exact match - no LIKE escaping needed
        stmt = select(users_models.Users).where(
            users_models.Users.username == normalized_username
        )
        return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_user_by_email(email: str, db: Session) -> users_models.Users | None:
    """
    Retrieve user by email address.

    Args:
        email: Email address to search for (case-insensitive).
        db: SQLAlchemy database session.

    Returns:
        Users model if found, None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(users_models.Users).where(users_models.Users.email == email.lower())
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_user_by_id(
    user_id: int, db: Session, public_check: bool = False
) -> users_models.Users | None:
    """
    Retrieve user by ID.

    Args:
        user_id: User ID to search for.
        db: SQLAlchemy database session.
        public_check: If True, only returns user when public sharing
                      is enabled in server settings.

    Returns:
        Users model if found (and public sharing enabled if
        public_check=True), None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    if public_check:
        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_utils.get_server_settings_or_404(db)

        # Return None if public sharable links are disabled
        if (
            not server_settings.public_shareable_links
            or not server_settings.public_shareable_links_user_info
        ):
            return None

    stmt = select(users_models.Users).where(users_models.Users.id == user_id)
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_users_admin(db: Session) -> list[users_models.Users]:
    """
    Retrieve all admin users from the database.

    Args:
        db: SQLAlchemy database session.

    Returns:
        List of User models with admin access.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(users_models.Users).where(
        users_models.Users.access_type == users_schema.UserAccessType.ADMIN.value
    )
    return db.execute(stmt).scalars().all()


@core_decorators.handle_db_errors
def create_user(
    user: users_schema.UsersCreate,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
) -> users_models.Users:
    """
    Create a new user with hashed password.

    Args:
        user: User creation data with plain text password.
        password_hasher: Password hasher instance.
        db: SQLAlchemy database session.

    Returns:
        Created Users model with hashed password.

    Raises:
        HTTPException: 409 if email/username already exists.
        HTTPException: 500 if database error occurs.
    """
    try:
        user.username = user.username.lower()
        user.email = user.email.lower()

        # Get server settings to determine password policy
        server_settings = server_settings_utils.get_server_settings_or_404(db)

        # Hash the password with configurable policy and length
        hashed_password = users_utils.check_password_and_hash(
            user.password, password_hasher, server_settings, user.access_type.value
        )

        # Create a new user
        db_user = users_models.Users(
            **user.model_dump(exclude={"password"}),
            password=hashed_password,
        )

        # Add the user to the database
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        # Return user
        return db_user
    except HTTPException:
        # Rollback the transaction
        db.rollback()
        raise
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Duplicate entry error. Check if email and username are unique"),
        ) from integrity_error


@core_decorators.handle_db_errors
def create_signup_user(
    user: users_schema.UsersSignup,
    server_settings: server_settings_schema.ServerSettingsRead,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
) -> users_models.Users:
    """
    Create a new user during signup process.

    Args:
        user: User signup data.
        server_settings: Server config for signup requirements.
        password_hasher: Password hasher instance.
        db: SQLAlchemy database session.

    Returns:
        Created Users model.

    Raises:
        HTTPException: 409 if email/username already exists. Abstract message
            to reduce information leakage.
        HTTPException: 500 if database error occurs.
    """
    try:
        # Determine user status based on server settings
        active = True
        email_verified = False
        pending_admin_approval = False

        if server_settings.signup_require_email_verification:
            email_verified = False
            active = False  # Inactive until email verified

        if server_settings.signup_require_admin_approval:
            pending_admin_approval = True
            active = False  # Inactive until approved

        # If both email verification and admin approval are disabled, user is immediately active
        if (
            not server_settings.signup_require_email_verification
            and not server_settings.signup_require_admin_approval
        ):
            active = True
            email_verified = True

        # Create a new user
        db_user = users_models.Users(
            **user.model_dump(
                exclude={
                    "username",
                    "email",
                    "access_type",
                    "active",
                    "email_verified",
                    "pending_admin_approval",
                    "password",
                }
            ),
            username=user.username.lower(),
            email=user.email.lower(),
            access_type=users_schema.UserAccessType.REGULAR.value,
            active=active,
            email_verified=email_verified,
            pending_admin_approval=pending_admin_approval,
            password=users_utils.check_password_and_hash(
                user.password,
                password_hasher,
                server_settings,
                users_schema.UserAccessType.REGULAR.value,
            ),
        )

        # Add the user to the database
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        # Return user
        return db_user
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Unable to create user."),
        ) from integrity_error


@core_decorators.handle_db_errors
async def edit_user(
    user_id: int, user: users_schema.UsersRead, db: Session
) -> users_models.Users:
    """
    Update an existing user's information.

    Args:
        user_id: ID of user to update.
        user: User data to update with.
        db: SQLAlchemy database session.

    Returns:
        users_models.Users

    Raises:
        HTTPException: 404 if user not found.
        HTTPException: 409 if email/username conflict.
        HTTPException: 500 if database error occurs.
    """
    try:
        # Get the user from the database
        db_user = users_utils.get_user_by_id_or_404(user_id, db)

        height_before = db_user.height

        # Check if the photo_path is being updated
        if user.photo_path:
            # Delete the user photo in the filesystem
            await users_utils.delete_user_photo_filesystem(db_user.id)

        user.username = user.username.lower()

        # Dictionary of the fields to update if they are not None
        user_data = user.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_user dynamically
        for key, value in user_data.items():
            setattr(db_user, key, value)

        # Commit the transaction
        db.commit()
        db.refresh(db_user)

        if height_before != db_user.height:
            # Update the user's health data
            health_weight_utils.calculate_bmi_all_user_entries(db_user.id, db)

        if db_user.photo_path is None:
            # Delete the user photo in the filesystem
            await users_utils.delete_user_photo_filesystem(db_user.id)

        return db_user
    except HTTPException:
        raise
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Duplicate entry error. " "Check if email and username are unique"),
        ) from integrity_error


@core_decorators.handle_db_errors
def approve_user(user_id: int, db: Session) -> None:
    """
    Approve a user by marking them as active.

    Args:
        user_id: ID of user to approve.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 if user not found.
        HTTPException: 400 if user email not verified.
        HTTPException: 500 if database error occurs.
    """
    # Get the user from the database
    db_user = users_utils.get_user_by_id_or_404(user_id, db)

    if not db_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User email is not verified",
        )

    db_user.pending_admin_approval = False
    db_user.active = True

    # Commit the transaction
    db.commit()
    db.refresh(db_user)


@core_decorators.handle_db_errors
def verify_user_email(
    user_id: int,
    server_settings: server_settings_schema.ServerSettingsRead,
    db: Session,
) -> None:
    """
    Verify user email and conditionally activate account.

    Args:
        user_id: ID of user to verify.
        server_settings: Server config determining activation policy.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 if user not found.
        HTTPException: 500 if database error occurs.
    """
    # Get the user from the database
    db_user = users_utils.get_user_by_id_or_404(user_id, db)

    db_user.email_verified = True
    if not server_settings.signup_require_admin_approval:
        db_user.pending_admin_approval = False
        db_user.active = True

    # Commit the transaction
    db.commit()
    db.refresh(db_user)


@core_decorators.handle_db_errors
def edit_user_password(
    user_id: int,
    password: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
    is_hashed: bool = False,
) -> None:
    """
    Update a user's password.

    Args:
        user_id: ID of user to update password for.
        password: New password (plain text or hashed based on is_hashed).
        password_hasher: Password hasher instance.
        db: SQLAlchemy database session.
        is_hashed: Whether password is already hashed.

    Returns:
        None

    Raises:
        HTTPException: 404 if user not found.
        HTTPException: 500 if database error occurs.
    """
    # Get the user from the database
    db_user = users_utils.get_user_by_id_or_404(user_id, db)

    # Update the user
    if is_hashed:
        db_user.password = password
    else:
        # Get server settings to determine password policy
        server_settings = server_settings_utils.get_server_settings_or_404(db)

        # Hash the password with configurable policy and length
        db_user.password = users_utils.check_password_and_hash(
            password, password_hasher, server_settings, db_user.access_type
        )

    # Commit the transaction
    db.commit()
    db.refresh(db_user)


@core_decorators.handle_db_errors
async def update_user_photo(
    user_id: int, db: Session, photo_path: str | None = None
) -> str | None:
    """
    Update a user's photo path.

    Args:
        user_id: ID of user to update photo for.
        db: SQLAlchemy database session.
        photo_path: New photo path. If None, removes photo.

    Returns:
        The updated photo path, or None if removed.

    Raises:
        HTTPException: 404 if user not found.
        HTTPException: 500 if database error occurs.
    """
    # Get the user from the database
    db_user = users_utils.get_user_by_id_or_404(user_id, db)

    # Update the user
    db_user.photo_path = photo_path

    # Commit the transaction
    db.commit()
    db.refresh(db_user)

    if photo_path:
        # Return the photo path
        return photo_path
    else:
        # Delete the user photo in the filesystem
        await users_utils.delete_user_photo_filesystem(user_id)

        return None


@core_decorators.handle_db_errors
def update_user_mfa(
    user_id: int, db: Session, encrypted_secret: str | None = None
) -> None:
    """
    Update a user's MFA settings.

    Args:
        user_id: ID of user to update MFA for.
        db: SQLAlchemy database session.
        encrypted_secret: Encrypted MFA secret. If None, disables MFA.

    Returns:
        None

    Raises:
        HTTPException: 404 if user not found.
        HTTPException: 500 if database error occurs.
    """
    # Get the user from the database
    db_user = users_utils.get_user_by_id_or_404(user_id, db)

    if encrypted_secret:
        db_user.mfa_enabled = True
        db_user.mfa_secret = encrypted_secret
    else:
        db_user.mfa_enabled = False
        db_user.mfa_secret = None

    db.commit()
    db.refresh(db_user)


@core_decorators.handle_db_errors
async def delete_user(user_id: int, db: Session) -> None:
    """
    Delete a user from the database.

    Args:
        user_id: ID of user to delete.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 if user not found.
        HTTPException: 500 if database error occurs.
    """
    # Get the user from the database
    db_user = users_utils.get_user_by_id_or_404(user_id, db)

    # Delete the user
    db.delete(db_user)

    # Commit the transaction
    db.commit()

    # Delete the user photo in the filesystem
    await users_utils.delete_user_photo_filesystem(user_id)
