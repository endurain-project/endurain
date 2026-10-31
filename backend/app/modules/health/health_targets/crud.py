"""CRUD operations for per-user health targets."""

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.health.computation as health_computation
import modules.health.health_targets.models as health_targets_models
import modules.health.health_targets.schema as health_targets_schema
import modules.health.record_crud as health_record_crud

SPEC = health_record_crud.RecordSpec(
    model=health_targets_models.HealthTargets,
    read_schema=health_targets_schema.HealthTargetsRead,
    not_found="Health targets not found",
    etag_label="health targets",
)


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

    return (
        health_computation.to_read_schema(health_targets_schema.HealthTargetsRead, db_health_targets)
        if db_health_targets
        else None
    )


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
    row = health_targets_models.HealthTargets(user_id=user_id)
    return health_record_crud.add(
        SPEC, row, db, conflict="Duplicate entry error. Check if there is already an entry created for the user"
    )


def edit_health_targets(
    health_target: health_targets_schema.HealthTargetsUpdate,
    user_id: int,
    db: Session,
    *,
    if_match: str,
) -> health_targets_schema.HealthTargetsRead:
    """Stage an update to a user's health targets.

    Args:
        health_target: Schema with the fields to update.
        user_id: The ID of the user to update targets for.
        db: SQLAlchemy database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated targets.

    Raises:
        NotFoundError: If the user has no targets.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    stmt = select(health_targets_models.HealthTargets).where(health_targets_models.HealthTargets.user_id == user_id)
    db_health_target = db.execute(stmt).scalar_one_or_none()

    if db_health_target is None:
        raise core_exceptions.NotFoundError(SPEC.not_found)

    return health_record_crud.edit_row(SPEC, db_health_target, health_target, db, if_match=if_match)


def health_targets_exists(user_id: int, db: Session) -> bool:
    """Report whether a user has health targets.

    Args:
        user_id: The targets' owner.
        db: Database session.

    Returns:
        True when the user has targets.
    """
    stmt = select(
        select(health_targets_models.HealthTargets.id)
        .where(health_targets_models.HealthTargets.user_id == user_id)
        .exists()
    )
    return bool(db.execute(stmt).scalar())
