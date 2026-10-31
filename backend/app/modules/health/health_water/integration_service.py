"""The operations other modules may call on health water intake records.

The writes stage; the caller owns the unit of work and commits.
"""

from sqlalchemy.orm import Session

import modules.health.health_water.crud as health_water_crud
import modules.health.health_water.schema as health_water_schema
import modules.health.health_water.service as health_water_service


def get_health_water_by_date(user_id: int, date: str, db: Session) -> health_water_schema.HealthWaterRead | None:
    """Return a user's water intake record for a date, or ``None``.

    Args:
        user_id: The record's owner.
        date: The record's date.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    return health_water_crud.get_health_water_by_date_and_user_id(user_id, date, db)


def list_health_water(user_id: int, db: Session) -> list[health_water_schema.HealthWaterRead]:
    """Return all of a user's water intake records, newest first.

    Args:
        user_id: The records' owner.
        db: Database session.

    Returns:
        The records.
    """
    return health_water_crud.get_health_water_by_user_id(user_id, db)


def upsert_health_water(
    user_id: int, health_water: health_water_schema.HealthWaterCreate, db: Session
) -> health_water_schema.HealthWaterRead:
    """Stage a water record for a user, or replace the amount of their record for the same date.

    Args:
        user_id: The record's owner.
        health_water: The record to store.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    return health_water_service.stage_upsert_health_water(user_id, health_water, db)
