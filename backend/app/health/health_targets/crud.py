from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import health.health_targets.models as health_targets_models
import health.health_targets.schema as health_targets_schema

import core.logger as core_logger


def get_health_targets_by_user_id(
    user_id: int, db: Session
) -> health_targets_models.HealthTargets | None:
    """
    Retrieve health targets for a specific user.

    Args:
        user_id: The ID of the user to fetch targets for.
        db: SQLAlchemy database session.

    Returns:
        The HealthTargets model if found, None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    try:
        # Get the health_targets from the database
        stmt = select(health_targets_models.HealthTargets).where(
            health_targets_models.HealthTargets.user_id == user_id
        )
        return db.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_health_targets_by_user_id: " f"{db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def create_health_targets(
    user_id: int, db: Session
) -> health_targets_schema.HealthTargetsRead:
    """
    Create new health targets for a user.

    Args:
        user_id: The ID of the user to create targets for.
        db: SQLAlchemy database session.

    Returns:
        The created HealthTargetsRead schema.

    Raises:
        HTTPException: 409 error if targets already exist.
        HTTPException: 500 error if database operation fails.
    """
    try:
        # Create a new health_target
        db_health_targets = health_targets_models.HealthTargets(
            user_id=user_id,
            weight=None,
        )

        # Add the health_targets to the database
        db.add(db_health_targets)
        db.commit()
        db.refresh(db_health_targets)

        health_targets = health_targets_schema.HealthTargetsRead(
            id=db_health_targets.id,
            user_id=user_id,
        )

        # Return the health_targets
        return health_targets
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate entry error. Check if there is "
            "already an entry created for the user",
        ) from integrity_error
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in create_health_targets: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def edit_health_target(
    health_target: health_targets_schema.HealthTargetsUpdate,
    user_id: int,
    db: Session,
) -> health_targets_models.HealthTargets:
    """
    Update health targets for a specific user.

    Args:
        health_target: Schema with fields to update.
        user_id: The ID of the user to update targets for.
        db: SQLAlchemy database session.

    Returns:
        The updated HealthTargets model.

    Raises:
        HTTPException: 404 error if targets not found.
        HTTPException: 500 error if database operation fails.
    """
    try:
        # Get the user health target from the database
        db_health_target = get_health_targets_by_user_id(user_id, db)

        if db_health_target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User health target not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Dictionary of the fields to update if they are not None
        health_target_data = health_target.model_dump(exclude_unset=True)
        # Iterate over the fields and update dynamically
        for key, value in health_target_data.items():
            setattr(db_health_target, key, value)

        # Commit the transaction
        db.commit()
        db.refresh(db_health_target)

        return db_health_target
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in edit_health_target: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err
