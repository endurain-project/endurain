"""The operations other modules may call on health targets.

The writes stage; the caller owns the unit of work and commits.
"""

from sqlalchemy.orm import Session

import modules.health.health_targets.crud as health_targets_crud
import modules.health.health_targets.schema as health_targets_schema


def get_health_targets(user_id: int, db: Session) -> health_targets_schema.HealthTargetsRead | None:
    """Return a user's health targets, or ``None`` when they have none.

    Args:
        user_id: The targets' owner.
        db: Database session.

    Returns:
        The user's targets, or ``None``.
    """
    return health_targets_crud.get_health_targets_by_user_id(user_id, db)


def create_health_targets(user_id: int, db: Session) -> health_targets_schema.HealthTargetsRead:
    """Stage empty health targets for a new user.

    Args:
        user_id: The targets' owner.
        db: Database session.

    Returns:
        The staged targets.

    Raises:
        ConflictError: If the user already has targets.
    """
    return health_targets_crud.create_health_targets(user_id, db)


def edit_health_targets(
    health_targets: health_targets_schema.HealthTargetsUpdate,
    user_id: int,
    db: Session,
) -> health_targets_schema.HealthTargetsRead:
    """Stage an update to a user's health targets.

    Args:
        health_targets: The fields to update.
        user_id: The targets' owner.
        db: Database session.

    Returns:
        The updated targets.

    Raises:
        NotFoundError: If the user has no targets.
    """
    # The caller is a system writer (the profile importer), so it names no version.
    return health_targets_crud.edit_health_targets(health_targets, user_id, db, if_match="*")
