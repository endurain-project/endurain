"""CRUD operations for per-user health targets."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.health.health_targets.models as health_targets_models
import modules.health.health_targets.schema as health_targets_schema
import modules.health.health_targets.serializers as health_targets_serializers


def get_health_targets_by_user_id(user_id: int, db: Session) -> health_targets_schema.HealthTargetsRead | None:
    """Retrieve health targets for a specific user.

    Args:
        user_id: The ID of the user to fetch targets for.
        db: SQLAlchemy database session.

    Returns:
        The user's targets, or ``None`` when they have none.
    """
    stmt = select(health_targets_models.HealthTargets).where(health_targets_models.HealthTargets.user_id == user_id)
    db_health_targets = db.execute(stmt).scalar_one_or_none()

    return health_targets_serializers.to_read_schema(db_health_targets) if db_health_targets else None


def create_health_targets(user_id: int, db: Session) -> health_targets_schema.HealthTargetsRead:
    """Stage empty health targets for a user.

    Args:
        user_id: The ID of the user to create targets for.
        db: SQLAlchemy database session.

    Returns:
        The staged targets.

    Raises:
        ConflictError: If the user already has targets.
    """
    db_health_targets = health_targets_models.HealthTargets(user_id=user_id)

    try:
        db.add(db_health_targets)
        db.flush()
        db.refresh(db_health_targets)
    except IntegrityError as err:
        raise core_exceptions.ConflictError(
            "Duplicate entry error. Check if there is already an entry created for the user"
        ) from err

    return health_targets_serializers.to_read_schema(db_health_targets)


def edit_health_target(
    health_target: health_targets_schema.HealthTargetsUpdate,
    user_id: int,
    db: Session,
) -> health_targets_schema.HealthTargetsRead:
    """Stage an update to a user's health targets.

    Args:
        health_target: Schema with the fields to update.
        user_id: The ID of the user to update targets for.
        db: SQLAlchemy database session.

    Returns:
        The updated targets.

    Raises:
        NotFoundError: If the user has no targets.
    """
    stmt = select(health_targets_models.HealthTargets).where(health_targets_models.HealthTargets.user_id == user_id)
    db_health_target = db.execute(stmt).scalar_one_or_none()

    if db_health_target is None:
        raise core_exceptions.NotFoundError("Health targets not found")

    for key, value in health_target.model_dump(exclude_unset=True).items():
        setattr(db_health_target, key, value)

    db.flush()
    db.refresh(db_health_target)

    return health_targets_serializers.to_read_schema(db_health_target)
