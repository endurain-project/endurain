"""The operations other modules may call on health steps records.

The writes stage; the caller owns the unit of work and commits.
"""

from sqlalchemy.orm import Session

import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.schema as health_steps_schema
import modules.health.health_steps.service as health_steps_service


def get_health_steps_by_date(user_id: int, date: str, db: Session) -> health_steps_schema.HealthStepsRead | None:
    """Return a user's steps record for a date, or ``None``.

    Args:
        user_id: The record's owner.
        date: The record's date.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    return health_steps_crud.get_health_steps_by_date_and_user_id(user_id, date, db)


def create_health_steps(
    user_id: int, health_steps: health_steps_schema.HealthStepsCreate, db: Session
) -> health_steps_schema.HealthStepsRead:
    """Stage a steps record for a user.

    Args:
        user_id: The record's owner.
        health_steps: The record to create.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the user already has a record for that date.
    """
    return health_steps_crud.create_health_steps(user_id, health_steps, db)


def edit_health_steps(
    user_id: int, health_steps: health_steps_schema.HealthStepsUpdate, db: Session
) -> health_steps_schema.HealthStepsRead:
    """Stage an update to a user's steps record.

    Args:
        user_id: The record's owner.
        health_steps: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        PermissionDeniedError: If the record names another user.
        NotFoundError: If the user has no such record.
    """
    return health_steps_service.stage_edit_health_steps(user_id, health_steps, db)
