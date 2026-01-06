from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from urllib.parse import unquote

import auth.security as auth_security
import auth.password_hasher as auth_password_hasher

import users.user.schema as users_schema
import users.user.utils as users_utils
import users.user.models as users_models
import users.user_identity_providers.crud as user_idp_crud

import health.health_weight.utils as health_weight_utils

import server_settings.utils as server_settings_utils
import server_settings.schema as server_settings_schema

import core.logger as core_logger


def authenticate_user(username: str, db: Session) -> users_models.User | None:
    try:
        user = (
            db.query(users_models.User)
            .filter(users_models.User.username == username.lower())
            .first()
        )

        return user
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in authenticate_user: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to authenticate user",
        ) from err


def get_all_users(db: Session):
    try:
        # Get the number of users from the database
        return db.query(users_models.User).all()
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_all_number: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_users_number(db: Session):
    try:
        # Get the number of users from the database
        return db.query(users_models.User.username).count()

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_users_number: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_users_with_pagination(db: Session, page_number: int = 1, num_records: int = 5):
    try:
        # Get the users from the database and format the birthdate
        users = [
            users_utils.format_user_birthdate(user)
            for user in db.query(users_models.User)
            .order_by(users_models.User.username)
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        ]

        # If the users were not found, return None
        if not users:
            return None

        # Enrich users with IDP count
        for user in users:
            idp_links = user_idp_crud.get_user_identity_providers_by_user_id(
                user.id, db
            )
            user.external_auth_count = len(idp_links)

        # Return the users
        return users
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_users_with_pagination: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_if_contains_username(username: str, db: Session):
    try:
        # Define a search term
        partial_username = unquote(username).replace("+", " ").lower()

        # Get the user from the database
        users = (
            db.query(users_models.User)
            .filter(
                func.lower(users_models.User.username).like(f"%{partial_username}%")
            )
            .all()
        )

        # If the user was not found, return None
        if users is None:
            return None

        # Format the birthdate
        users = [users_utils.format_user_birthdate(user) for user in users]

        # Return the user
        return users
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_if_contains_username: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_by_username(username: str, db: Session):
    try:
        # Get the user from the database
        user = (
            db.query(users_models.User)
            .filter(users_models.User.username == username)
            .first()
        )

        # If the user was not found, return None
        if user is None:
            return None

        # Format the birthdate
        user = users_utils.format_user_birthdate(user)

        # Return the user
        return user
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_by_username: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_by_email(email: str, db: Session):
    try:
        # Get the user from the database
        user = (
            db.query(users_models.User)
            .filter(users_models.User.email == email.lower())
            .first()
        )

        # If the user was not found, return None
        if user is None:
            return None

        # Format the birthdate
        user = users_utils.format_user_birthdate(user)

        # Return the user
        return user
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_user_by_email: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_by_id(user_id: int, db: Session):
    try:
        # Get the user from the database
        user = (
            db.query(users_models.User).filter(users_models.User.id == user_id).first()
        )

        # If the user was not found, return None
        if user is None:
            return None

        # Format the birthdate
        user = users_utils.format_user_birthdate(user)

        # Return the user
        return user
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_user_by_id: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_by_id_if_is_public(user_id: int, db: Session):
    try:
        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_utils.get_server_settings(db)

        # Return None if public sharable links are disabled
        if (
            not server_settings.public_shareable_links
            or not server_settings.public_shareable_links_user_info
        ):
            return None

        # Get the user from the database
        user = (
            db.query(users_models.User).filter(users_models.User.id == user_id).first()
        )

        # If the user was not found, return None
        if user is None:
            return None

        # Format the birthdate
        user = users_utils.format_user_birthdate(user)

        # Return the user
        return user
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_by_id_if_is_public: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_users_admin(db: Session):
    try:
        # Get the users from the database and format the birthdate
        users = [
            users_utils.format_user_birthdate(user)
            for user in db.query(users_models.User)
            .filter(users_models.User.access_type == 2)
            .all()
        ]

        # If the users were not found, return None
        if not users:
            return None

        # Return the users
        return users
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_users_admin: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_user(
    user: users_schema.UserCreate,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
):
    try:
        user.username = user.username.lower()
        user.email = user.email.lower()

        # Get server settings to determine password policy
        server_settings = server_settings_utils.get_server_settings(db)

        # Hash the password with configurable policy and length
        hashed_password = users_utils.check_password_and_hash(
            user.password, password_hasher, server_settings, user.access_type
        )

        # Create a new user
        db_user = users_models.User(
            **user.model_dump(exclude={"password"}),
            password=hashed_password,
        )

        # Add the user to the database
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        # Return user
        return db_user
    except HTTPException as http_err:
        # Rollback the transaction
        db.rollback()

        # Raise exception
        raise http_err
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate entry error. Check if email and username are unique",
        ) from integrity_error
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in create_user: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        ) from err


def edit_user(user_id: int, user: users_schema.UserRead, db: Session):
    try:
        # Get the user from the database
        db_user = (
            db.query(users_models.User).filter(users_models.User.id == user_id).first()
        )

        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        height_before = db_user.height

        # Check if the photo_path is being updated
        if user.photo_path:
            # Delete the user photo in the filesystem
            users_utils.delete_user_photo_filesystem(db_user.id)

        user.username = user.username.lower()

        # Dictionary of the fields to update if they are not None
        user_data = user.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_user dynamically
        for key, value in user_data.items():
            setattr(db_user, key, value)

        # Commit the transaction
        db.commit()

        if height_before != db_user.height:
            # Update the user's health data
            health_weight_utils.calculate_bmi_all_user_entries(user_id, db)

        if db_user.photo_path is None:
            # Delete the user photo in the filesystem
            users_utils.delete_user_photo_filesystem(db_user.id)
    except HTTPException as http_err:
        raise http_err
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate entry error. Check if email and username are unique",
        ) from integrity_error
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in edit_user: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def approve_user(user_id: int, db: Session):
    """
    Approve a user by ID.

    Fetches the user with the given user_id from the provided SQLAlchemy Session.
    If the user exists and their email is verified, marks the user as approved by
    setting `pending_admin_approval` to False and `active` to True, then commits
    the transaction.

    Parameters:
        user_id (int): The primary key of the user to approve.
        db (Session): SQLAlchemy Session used for querying and committing changes.

    Raises:
        HTTPException: 404 Not Found if no user with the given ID exists. The
            raised exception includes a "WWW-Authenticate: Bearer" header.
        HTTPException: 400 Bad Request if the user exists but their email has not
            been verified.
        HTTPException: 500 Internal Server Error for any unexpected error during
            processing; the function will rollback the transaction and log the
            original exception before raising this error.

    Side effects:
        - Updates the user object by setting `pending_admin_approval = False` and
          `active = True`.
        - Commits the DB transaction on success.
        - Rolls back the DB transaction and logs the error via
          `core_logger.print_to_log` on unexpected failures.

    Returns:
        None

    Notes:
        - The function expects the `users_models.User` model to be importable and the
          provided `db` to be a working SQLAlchemy session.
        - The original exception is chained to the re-raised 500 HTTPException to
          preserve context for debugging.
    """
    try:
        # Get the user from the database
        db_user = (
            db.query(users_models.User).filter(users_models.User.id == user_id).first()
        )

        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not db_user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User email is not verified",
            )

        db_user.pending_admin_approval = False
        db_user.active = True

        # Commit the transaction
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in approve_user: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def verify_user_email(
    user_id: int,
    server_settings: server_settings_schema.ServerSettingsRead,
    db: Session,
):
    """
    Verify a user's email and update their account status in the database.

    Parameters
    ----------
    user_id : int
        The primary key of the user to verify.
    server_settings : server_settings_schema.ServerSettingsRead
        Server configuration used to determine whether admin approval is required
        (controls whether the account should be activated immediately).
    db : Session
        SQLAlchemy session used to query and persist changes to the database.

    Returns
    -------
    None

    Side effects
    ------------
    - Marks the user's email as verified (sets db_user.email_verified = True).
    - If server_settings.signup_require_admin_approval is False:
      - Clears pending admin approval (db_user.pending_admin_approval = False).
      - Activates the user account (db_user.active = True).
    - Commits the transaction on success.
    - On unexpected errors, rolls back the transaction and logs the exception via core_logger.print_to_log.

    Raises
    ------
    HTTPException
        - 404 Not Found: if no user exists with the provided user_id.
        - Re-raises any HTTPException raised during processing.
        - 500 Internal Server Error: for unexpected exceptions encountered while updating the database.

    Notes
    -----
    - The function queries users_models.User for the given user_id.
    - The caller is responsible for managing the lifecycle of the provided DB session.
    """
    try:
        # Get the user from the database
        db_user = (
            db.query(users_models.User).filter(users_models.User.id == user_id).first()
        )

        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        db_user.email_verified = True
        if not server_settings.signup_require_admin_approval:
            db_user.pending_admin_approval = False
            db_user.active = True

        # Commit the transaction
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in verify_user_email: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_user_password(
    user_id: int,
    password: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
    is_hashed: bool = False,
):
    try:
        # Get the user from the database
        db_user = (
            db.query(users_models.User).filter(users_models.User.id == user_id).first()
        )

        # Update the user
        if is_hashed:
            db_user.password = password
        else:
            # Get server settings to determine password policy
            server_settings = server_settings_utils.get_server_settings(db)

            # Hash the password with configurable policy and length
            db_user.password = users_utils.check_password_and_hash(
                password, password_hasher, server_settings, db_user.access_type
            )

        # Commit the transaction
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in edit_user_password: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to edit user password",
        ) from err


def edit_user_photo_path(user_id: int, photo_path: str, db: Session):
    try:
        # Get the user from the database
        db_user = (
            db.query(users_models.User).filter(users_models.User.id == user_id).first()
        )

        # Update the user
        db_user.photo_path = photo_path

        # Commit the transaction
        db.commit()

        # Return the photo path
        return photo_path
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in edit_user_photo_path: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_user_photo(user_id: int, db: Session):
    try:
        # Get the user from the database
        db_user = (
            db.query(users_models.User).filter(users_models.User.id == user_id).first()
        )

        # Update the user
        db_user.photo_path = None

        # Commit the transaction
        db.commit()

        # Delete the user photo in the filesystem
        users_utils.delete_user_photo_filesystem(user_id)
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in delete_user_photo: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_user(user_id: int, db: Session):
    try:
        # Delete the user
        num_deleted = (
            db.query(users_models.User).filter(users_models.User.id == user_id).delete()
        )

        # Check if the user was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found",
            )

        # Commit the transaction
        db.commit()

        # Delete the user photo in the filesystem
        users_utils.delete_user_photo_filesystem(user_id)
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in delete_user: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def enable_user_mfa(user_id: int, encrypted_secret: str, db: Session):
    """
    Enable multi-factor authentication (MFA) for a user.

    This function looks up the user by user_id, sets the user's MFA flag and
    stores the provided encrypted secret, then commits the change to the database.

    Parameters
    ----------
    user_id : int
        ID of the user to enable MFA for.
    encrypted_secret : str
        Encrypted MFA secret to be stored on the user record.
    db : Session
        Active SQLAlchemy session used to query and persist the user.

    Returns
    -------
    None

    Raises
    ------
    HTTPException
        - 404 Not Found: if no user exists with the given user_id (includes
          header {"WWW-Authenticate": "Bearer"}).
        - 500 Internal Server Error: if any unexpected error occurs while updating
          the database (the transaction will be rolled back and the error logged).

    Side effects
    ------------
    - Sets user.mfa_enabled = True and user.mfa_secret = encrypted_secret.
    - Commits the transaction on success and refreshes the user instance.
    - Rolls back the transaction and logs the exception on failure.
    """
    try:
        db_user = (
            db.query(users_models.User).filter(users_models.User.id == user_id).first()
        )

        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        db_user.mfa_enabled = True
        db_user.mfa_secret = encrypted_secret
        db.commit()
        db.refresh(db_user)
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(f"Error in enable_user_mfa: {err}", "error", exc=err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def disable_user_mfa(user_id: int, db: Session):
    """
    Disable multi-factor authentication (MFA) for a user.
    Looks up the user by the given user_id using the provided SQLAlchemy Session,
    disables MFA by setting `mfa_enabled` to False and clearing `mfa_secret`, then
    commits the change and refreshes the user instance from the database.
    Args:
        user_id (int): ID of the user whose MFA should be disabled.
        db (Session): SQLAlchemy Session for database operations.
    Returns:
        None
    Raises:
        HTTPException:
            - 404 Not Found if the user does not exist.
            - 500 Internal Server Error for any other failure; in this case the
              transaction is rolled back and the error is logged.
    Side effects:
        - Persists changes to the database (commit).
        - Clears the user's MFA secret and marks MFA as disabled.
        - Refreshes the in-memory user object to reflect persisted state.
    """
    try:
        db_user = (
            db.query(users_models.User).filter(users_models.User.id == user_id).first()
        )

        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        db_user.mfa_enabled = False
        db_user.mfa_secret = None
        db.commit()
        db.refresh(db_user)
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(f"Error in disable_user_mfa: {err}", "error", exc=err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_signup_user(
    user: users_schema.UserSignup,
    server_settings: server_settings_schema.ServerSettingsRead,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
):
    """
    Creates a new user during the signup process, handling email verification and admin approval requirements.

    Args:
        user (users_schema.UserSignup): The user signup data containing user details.
        server_settings (server_settings_schema.ServerSettingsRead): Server settings used to determine if email verification or admin approval is required.
        password_hasher (auth_password_hasher.PasswordHasher): Password hasher used to hash the user's password.
        db (Session): SQLAlchemy database session.

    Returns:
        users_models.User: The newly created user object.

    Raises:
        HTTPException:
            - 409 Conflict if the email or username is not unique.
            - 500 Internal Server Error for any other exceptions.
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
        db_user = users_models.User(
            name=user.name,
            username=user.username.lower(),
            email=user.email.lower(),
            city=user.city,
            birthdate=user.birthdate,
            preferred_language=user.preferred_language,
            gender=user.gender,
            units=user.units,
            height=user.height,
            access_type=users_schema.UserAccessType.REGULAR,
            active=active,
            first_day_of_week=user.first_day_of_week,
            currency=user.currency,
            email_verified=email_verified,
            pending_admin_approval=pending_admin_approval,
            password=users_utils.check_password_and_hash(
                user.password,
                password_hasher,
                server_settings,
                users_schema.UserAccessType.REGULAR,
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
            detail="Duplicate entry error. Check if email and username are unique",
        ) from integrity_error
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_signup_user: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
