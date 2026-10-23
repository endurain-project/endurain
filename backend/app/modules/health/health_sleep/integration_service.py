"""The operations other modules may call on health sleep records."""

from sqlalchemy.orm import Session

import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.schema as health_sleep_schema


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
    """Create a sleep record for a user.

    Args:
        user_id: The record's owner.
        health_sleep: The record to create.
        db: Database session.

    Returns:
        The created record.
    """
    return health_sleep_crud.create_health_sleep(user_id, health_sleep, db)


def edit_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepUpdate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Edit a user's sleep record.

    Args:
        user_id: The record's owner.
        health_sleep: The record with its changes.
        db: Database session.

    Returns:
        The edited record.
    """
    return health_sleep_crud.edit_health_sleep(user_id, health_sleep, db)
