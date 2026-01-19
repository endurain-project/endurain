"""CRUD operations for user default gear."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import users.users_default_gear.models as user_default_gear_models
import users.users_default_gear.schema as user_default_gear_schema

import core.decorators as core_decorators


@core_decorators.handle_db_errors
def get_user_default_gear_by_user_id(
    user_id: int,
    db: Session,
) -> user_default_gear_models.UsersDefaultGear | None:
    """
    Retrieve default gear settings for a specific user.

    Args:
        user_id: The ID of the user to fetch settings for.
        db: SQLAlchemy database session.

    Returns:
        The UsersDefaultGear model for the user or None if not found.

    Raises:
        HTTPException: 404 error if settings not found.
        HTTPException: 500 error if database query fails.
    """
    stmt = select(user_default_gear_models.UsersDefaultGear).where(
        user_default_gear_models.UsersDefaultGear.user_id == user_id
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def create_user_default_gear(
    user_id: int,
    db: Session,
) -> user_default_gear_models.UsersDefaultGear:
    """
    Create default gear settings for a user.

    Args:
        user_id: The ID of the user to create settings for.
        db: SQLAlchemy database session.

    Returns:
        The created UsersDefaultGear model.

    Raises:
        HTTPException: 409 error if settings already exist.
        HTTPException: 500 error if database operation fails.
    """
    try:
        db_default_gear = user_default_gear_models.UsersDefaultGear(
            user_id=user_id,
        )

        db.add(db_default_gear)
        db.commit()
        db.refresh(db_default_gear)

        return db_default_gear
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Default gear settings already exist for this user"),
        ) from integrity_error


@core_decorators.handle_db_errors
def edit_user_default_gear(
    user_default_gear: user_default_gear_schema.UsersDefaultGearUpdate,
    user_id: int,
    db: Session,
) -> user_default_gear_models.UsersDefaultGear:
    """
    Update default gear settings for a user.

    Args:
        user_default_gear: Schema with gear fields to update.
        user_id: The ID of the user.
        db: SQLAlchemy database session.

    Returns:
        The updated UsersDefaultGear model.

    Raises:
        HTTPException: 404 error if settings not found.
        HTTPException: 500 error if database operation fails.
    """
    if user_default_gear.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit default gear for another user.",
        )

    db_user_default_gear = get_user_default_gear_by_user_id(user_id, db)

    if db_user_default_gear is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User default gear not found",
        )

    user_default_gear_data = user_default_gear.model_dump(
        exclude_unset=True, exclude={"user_id", "id"}
    )
    for key, value in user_default_gear_data.items():
        setattr(db_user_default_gear, key, value)

    db.commit()
    db.refresh(db_user_default_gear)

    return db_user_default_gear
