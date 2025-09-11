from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from urllib.parse import unquote

import session.security as session_security

import users.user.schema as users_schema
import users.user.utils as users_utils
import users.user.models as users_models

import health_data.utils as health_data_utils

import sign_up_tokens.utils as sign_up_tokens_utils

import server_settings.utils as server_settings_utils

import core.logger as core_logger
import core.apprise as core_apprise


def authenticate_user(username: str, db: Session):
    try:
        user = (
            db.query(users_models.User)
            .filter(users_models.User.username == username)
            .first()
        )

        if not user:
            return None
        return user
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in authenticate_user: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
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
            db.query(users_models.User).filter(users_models.User.email == email).first()
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


def create_user(user: users_schema.UserCreate, db: Session):
    try:
        # Create a new user
        db_user = users_models.User(
            **user.model_dump(exclude={"password"}),
            password=session_security.hash_password(user.password),
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
        core_logger.print_to_log(f"Error in create_user: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_user(user_id: int, user: users_schema.User, db: Session):
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

        # If the user photo path is different, delete the user photo in the filesystem
        if db_user.photo_path != user.photo_path:
            # Delete the user photo in the filesystem
            users_utils.delete_user_photo_filesystem(db_user.id)

        # Dictionary of the fields to update if they are not None
        user_data = user.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_user dynamically
        for key, value in user_data.items():
            setattr(db_user, key, value)

        # Commit the transaction
        db.commit()

        if height_before != db_user.height:
            # Update the user's health data
            health_data_utils.calculate_bmi_all_user_entries(user_id, db)

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


async def approve_user(
    user_id: int, email_service: core_apprise.AppriseService, db: Session
):
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

        # Get the server settings from the database
        server_settings = server_settings_utils.get_server_settings(db)

        user_can_login = False
        require_email_verification = False
        email_sent_success = False

        db_user.pending_admin_approval = False
        if server_settings.signup_require_email_verification:
            require_email_verification = True
            # Send the sign-up email
            email_sent_success = await sign_up_tokens_utils.send_sign_up_email(
                db_user, email_service, db
            )
        else:
            db_user.active = True
            db_user.email_verified = True
            user_can_login = True

        # Commit the transaction
        db.commit()

        return user_can_login, require_email_verification, email_sent_success
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


def edit_user_password(user_id: int, password: str, db: Session):
    try:
        # Get the user from the database
        db_user = (
            db.query(users_models.User).filter(users_models.User.id == user_id).first()
        )

        # Update the user
        db_user.password = session_security.hash_password(password)

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
            detail="Internal Server Error",
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
    server_settings,
    db: Session,
):
    """
    Creates a new user during the signup process, handling email verification and admin approval requirements.

    Args:
        user (users_schema.UserSignup): The user signup data containing user details.
        server_settings: Server configuration settings that determine signup requirements.
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
            username=user.username,
            email=user.email,
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
            password=session_security.hash_password(user.password),
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


""" def verify_user_email(token: str, db: Session):
    try:
        # Find user by verification token
        db_user = (
            db.query(users_models.User)
            .filter(users_models.User.email_verification_token == token)
            .first()
        )

        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid or expired verification token",
            )

        # Mark email as verified and remove token
        db_user.email_verified = True
        db_user.email_verification_token = None

        # If not pending admin approval, activate the user
        if not db_user.pending_admin_approval:
            db_user.active = True

        db.commit()
        db.refresh(db_user)

        return db_user
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
        ) from err """
