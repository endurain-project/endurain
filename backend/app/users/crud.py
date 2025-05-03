from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from urllib.parse import unquote

import session.security as session_security

import users.schema as users_schema
import users.utils as users_utils
import users.models as users_models

import health_data.utils as health_data_utils

import server_settings.crud as server_settings_crud

import core.logger as core_logger


def authenticate_user(username: str, db: Session):
    try:
        # Get the user from the database
        user = (
            db.query(users_models.User)
            .filter(users_models.User.username == username)
            .first()
        )

        # Check if the user exists and if the password is correct and if not return None
        if not user:
            return None

        # Return the user if the password is correct
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
        server_settings = server_settings_crud.get_server_settings(db)

        # Return None if public sharable links are disabled
        if (
            not server_settings
            or not server_settings.public_shareable_links
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
