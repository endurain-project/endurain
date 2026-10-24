"""The operations other modules may call on health water intake records."""

from sqlalchemy.orm import Session

import modules.health.health_water.crud as health_water_crud
import modules.health.health_water.schema as health_water_schema


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
