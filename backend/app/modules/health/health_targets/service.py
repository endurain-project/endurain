"""Application logic for per-user health targets.

The module's own application layer; what other modules may consume lives in
:mod:`modules.health.health_targets.integration_service`.
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.health.health_targets.crud as health_targets_crud
import modules.health.health_targets.schema as health_targets_schema

logger = core_logger.get_logger(__name__)


def get_health_targets(user_id: int, db: Session) -> health_targets_schema.HealthTargetsRead | None:
    """Return a user's health targets.

    Args:
        user_id: The targets' owner.
        db: Database session.

    Returns:
        The user's targets, or ``None`` when they have none.
    """
    return health_targets_crud.get_health_targets_by_user_id(user_id, db)


def update_health_targets(
    health_targets: health_targets_schema.HealthTargetsUpdate,
    user_id: int,
    db: Session,
) -> health_targets_schema.HealthTargetsRead:
    """Update a user's health targets and commit.

    Args:
        health_targets: The fields to update.
        user_id: The targets' owner.
        db: Database session.

    Returns:
        The updated targets.

    Raises:
        NotFoundError: If the user has no targets.
    """
    updated = health_targets_crud.edit_health_target(health_targets, user_id, db)
    db.commit()
    logger.info("Updated health targets", extra=core_logger.context(user_id=user_id))
    return updated
