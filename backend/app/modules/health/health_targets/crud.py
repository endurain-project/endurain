from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.health.health_targets.models as health_targets_models
import modules.health.health_targets.schema as health_targets_schema

# Private internal helpers


def _transform_health_targets(
    health_targets: health_targets_models.HealthTargets,
) -> health_targets_schema.HealthTargetsRead:
    """
    Transform a health targets ORM instance to a Pydantic schema.

    Args:
        health_targets: The health targets ORM instance.

    Returns:
        The health targets as a schema.
    """
    return health_targets_schema.HealthTargetsRead.model_validate(health_targets)


@core_decorators.handle_db_errors
def _get_health_targets_model_by_user_id_or_404(user_id: int, db: Session) -> health_targets_models.HealthTargets:
    """
    Retrieve health targets record model by user ID.

    Args:
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        Mapped ``HealthTargets`` ORM instance.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_targets from the database
    stmt = select(health_targets_models.HealthTargets).where(
        health_targets_models.HealthTargets.user_id == user_id,
    )
    db_health_targets = db.execute(stmt).scalar_one_or_none()

    if db_health_targets is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health targets not found",
        )

    return db_health_targets


# Public CRUD functions


@core_decorators.handle_db_errors
def get_health_targets_by_user_id(user_id: int, db: Session) -> health_targets_schema.HealthTargetsRead | None:
    """
    Retrieve health targets for a specific user.

    Args:
        user_id: The ID of the user to fetch targets for.
        db: SQLAlchemy database session.

    Returns:
        The HealthTargetsRead schema if found, None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    # Get the health_targets from the database
    stmt = select(health_targets_models.HealthTargets).where(health_targets_models.HealthTargets.user_id == user_id)
    db_health_targets = db.execute(stmt).scalar_one_or_none()

    return _transform_health_targets(db_health_targets) if db_health_targets else None


@core_decorators.handle_db_errors
def create_health_targets(user_id: int, db: Session) -> health_targets_schema.HealthTargetsRead:
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
        )

        # Add the health_targets to the database
        db.add(db_health_targets)
        db.commit()
        db.refresh(db_health_targets)

        # Return the health_targets
        return _transform_health_targets(db_health_targets)
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate entry error. Check if there is already an entry created for the user",
        ) from integrity_error


@core_decorators.handle_db_errors
def edit_health_target(
    health_target: health_targets_schema.HealthTargetsUpdate,
    user_id: int,
    db: Session,
) -> health_targets_schema.HealthTargetsRead:
    """
    Update health targets for a specific user.

    Args:
        health_target: Schema with fields to update.
        user_id: The ID of the user to update targets for.
        db: SQLAlchemy database session.

    Returns:
        The updated HealthTargetsRead schema.

    Raises:
        HTTPException: 404 error if targets not found.
        HTTPException: 500 error if database operation fails.
    """
    # Get the user health target from the database
    db_health_target = _get_health_targets_model_by_user_id_or_404(user_id=user_id, db=db)

    # Dictionary of the fields to update if they are not None
    health_target_data = health_target.model_dump(exclude_unset=True)
    # Iterate over the fields and update dynamically
    for key, value in health_target_data.items():
        setattr(db_health_target, key, value)

    # Commit the transaction
    db.commit()
    db.refresh(db_health_target)

    return _transform_health_targets(db_health_target)
