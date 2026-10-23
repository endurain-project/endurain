"""The operations other modules may call on health sleep records.

The writes stage; the caller owns the unit of work and commits. Records arrive
already scored by their provider, so nothing here scores them.
"""

from sqlalchemy.orm import Session

import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_sleep.service as health_sleep_service


def get_health_sleep_by_date(user_id: int, date: str, db: Session) -> health_sleep_schema.HealthSleepRead | None:
    """Return a user's sleep record for a date, or ``None``.

    Args:
        user_id: The record's owner.
        date: The record's date.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    return health_sleep_crud.get_health_sleep_by_date_and_user_id(user_id, date, db)


def create_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepCreate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Stage a sleep record for a user.

    Args:
        user_id: The record's owner.
        health_sleep: The record to create.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the user already has a record for that date.
    """
    return health_sleep_crud.create_health_sleep(user_id, health_sleep, db)


def edit_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepUpdate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Stage an update to a user's sleep record.

    Args:
        user_id: The record's owner.
        health_sleep: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        PermissionDeniedError: If the record names another user.
        NotFoundError: If the user has no such record.
    """
    return health_sleep_service.stage_edit_health_sleep(user_id, health_sleep, db)
