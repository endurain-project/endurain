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


def upsert_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepCreate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Stage a sleep record for a user, or an update to their record for the same date.

    Args:
        user_id: The record's owner.
        health_sleep: The record to store.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    return health_sleep_service.stage_upsert_health_sleep(user_id, health_sleep, db)


def list_health_sleep(user_id: int, db: Session) -> list[health_sleep_schema.HealthSleepRead]:
    """Return all of a user's sleep records, newest first.

    Args:
        user_id: The records' owner.
        db: Database session.

    Returns:
        The records.
    """
    return health_sleep_crud.get_health_sleep_by_user_id(user_id, db)
