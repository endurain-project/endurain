"""The operations other modules may call on health water intake records.

The writes stage; the caller owns the unit of work and commits.
"""

from sqlalchemy.orm import Session

import modules.health.health_water.crud as health_water_crud
import modules.health.health_water.schema as health_water_schema
import modules.health.health_water.service as health_water_service
import modules.users.users_profile.contracts as users_profile_contracts


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


def profile_section() -> users_profile_contracts.ProfileRecordsSection:
    """Return the water records' section of a profile export and import.

    Returns:
        The section, which exports a user's water records and stages the archived ones.
    """
    return users_profile_contracts.ProfileRecordsSection(
        key="health_water",
        export=health_water_crud.get_health_water_by_user_id,
        restore=health_water_service.restore_profile_records,
    )
