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


def upsert_health_steps(
    user_id: int, health_steps: health_steps_schema.HealthStepsCreate, db: Session
) -> health_steps_schema.HealthStepsRead:
    """Stage a steps record for a user, or an update to their record for the same date.

    Args:
        user_id: The record's owner.
        health_steps: The record to store.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    return health_steps_service.stage_upsert_health_steps(user_id, health_steps, db)


def list_health_steps(user_id: int, db: Session) -> list[health_steps_schema.HealthStepsRead]:
    """Return all of a user's steps records, newest first.

    Args:
        user_id: The records' owner.
        db: Database session.

    Returns:
        The records.
    """
    return health_steps_crud.get_health_steps_by_user_id(user_id, db)
