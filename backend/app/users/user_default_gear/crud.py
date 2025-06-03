from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import users.user_default_gear.models as user_default_gear_models
import users.user_default_gear.schema as user_default_gear_schema

import core.logger as core_logger


def get_user_default_gear_by_user_id(user_id: int, db: Session):
    try:
        # Get the user default gear by the user id
        user_default_gear = (
            db.query(user_default_gear_models.UsersDefaultGear)
            .filter(user_default_gear_models.UsersDefaultGear.user_id == user_id)
            .first()
        )

        # Check if user_default_gear is None and return None if it is
        if user_default_gear is None:
            # If the user was not found, return a 404 Not Found error
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User default gear not found",
            )

        # Return the user default gear
        return user_default_gear
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_default_gear_by_user_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_user_default_gear(user_id: int, db: Session):
    try:
        # Create a new user default gear
        user_default_gear = user_default_gear_models.UsersDefaultGear(
            user_id=user_id,
        )

        # Add the user default gear to the database
        db.add(user_default_gear)
        db.commit()
        db.refresh(user_default_gear)

        # Return the user default gear
        return user_default_gear
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_user_default_gear: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_user_default_gear(
    user_default_gear: user_default_gear_schema.UserDefaultGear, user_id: int, db: Session
):
    try:
        # Get the user default gear from the database
        db_user_default_gear = (
            db.query(user_default_gear_models.UsersDefaultGear)
            .filter(
                user_default_gear_models.UsersDefaultGear.user_id == user_id,
            )
            .first()
        )

        if db_user_default_gear is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User default gear not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Dictionary of the fields to update if they are not None
        user_default_gear_data = user_default_gear.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_user dynamically
        for key, value in user_default_gear_data.items():
            setattr(db_user_default_gear, key, value)

        # Commit the transaction
        db.commit()

        return db_user_default_gear
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in edit_user_default_gear: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error: {err}",
        ) from err
