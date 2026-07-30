"""CRUD operations for user default gear.

WARNING: Functions prefixed with `_` (underscore) are private and must not
be imported outside this module. They are internal implementation details.
Use only the public functions exported by users.users_default_gear.__init__
for external consumption.
"""

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.users.users_default_gear.models as users_default_gear_models
import modules.users.users_default_gear.schema as users_default_gear_schema

# Private internal helpers


def _transform_users_default_gear(
    users: users_default_gear_models.UsersDefaultGear,
) -> users_default_gear_schema.UsersDefaultGearRead:
    """
    Transform a user default gear instance to a Pydantic schema.

    Args:
        users: The user default gear ORM instance.

    Returns:
        The user default gear as a schema.
    """
    return users_default_gear_schema.UsersDefaultGearRead.model_validate(users)


def _get_user_default_gear_model_by_user_id_or_404(
    user_id: int,
    db: Session,
) -> users_default_gear_models.UsersDefaultGear:
    """
    Retrieve a mapped UsersDefaultGear ORM row by user ID or raise 404.

    This is a **private internal helper**. Do not import or call from
    outside this module. Use public CRUD functions instead (e.g.,
    ``get_user_default_gear_by_user_id()``, ``edit_user_default_gear()``,
    etc.).

    Args:
        user_id: User ID to search for.
        db: SQLAlchemy database session.

    Returns:
        Mapped ``UsersDefaultGear`` ORM instance.

    Raises:
        HTTPException: 404 if user not found.
    """
    stmt = select(users_default_gear_models.UsersDefaultGear).where(
        users_default_gear_models.UsersDefaultGear.user_id == user_id
    )
    db_users_default_gear = db.execute(stmt).scalar_one_or_none()

    if not db_users_default_gear:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User default gear not found",
        )

    return db_users_default_gear


# Public CRUD functions


@core_decorators.handle_db_errors
def get_user_default_gear_by_user_id(
    user_id: int,
    db: Session,
) -> users_default_gear_schema.UsersDefaultGearRead | None:
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
    stmt = select(users_default_gear_models.UsersDefaultGear).where(
        users_default_gear_models.UsersDefaultGear.user_id == user_id
    )
    db_users_default_gear = db.execute(stmt).scalar_one_or_none()
    return _transform_users_default_gear(db_users_default_gear) if db_users_default_gear else None


@core_decorators.handle_db_errors
def create_user_default_gear(
    user_id: int,
    db: Session,
) -> users_default_gear_schema.UsersDefaultGearRead:
    """
    Create default gear settings for a user.

    Args:
        user_id: The ID of the user to create settings for.
        db: SQLAlchemy database session.

    Returns:
        The created UsersDefaultGear schema.

    Raises:
        HTTPException: 409 error if settings already exist.
        HTTPException: 500 error if database operation fails.
    """
    try:
        db_users_default_gear = users_default_gear_models.UsersDefaultGear(
            user_id=user_id,
        )

        db.add(db_users_default_gear)
        db.commit()
        db.refresh(db_users_default_gear)

        return _transform_users_default_gear(db_users_default_gear)
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Default gear settings already exist for this user"),
        ) from integrity_error


@core_decorators.handle_db_errors
def edit_user_default_gear(
    user_default_gear: users_default_gear_schema.UsersDefaultGearUpdate,
    user_id: int,
    db: Session,
) -> users_default_gear_schema.UsersDefaultGearRead:
    """
    Update default gear settings for a user.

    Args:
        user_default_gear: Schema with gear fields to update.
        user_id: The ID of the user.
        db: SQLAlchemy database session.

    Returns:
        The updated UsersDefaultGear schema.

    Raises:
        HTTPException: 404 error if settings not found.
        HTTPException: 500 error if database operation fails.
    """
    if user_default_gear.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit default gear for another user.",
        )

    db_users_default_gear = _get_user_default_gear_model_by_user_id_or_404(user_id, db)

    user_default_gear_data: dict[str, Any] = user_default_gear.model_dump(exclude_unset=True, exclude={"user_id", "id"})
    for key, value in user_default_gear_data.items():
        setattr(db_users_default_gear, key, value)

    db.commit()
    db.refresh(db_users_default_gear)

    return _transform_users_default_gear(db_users_default_gear)
