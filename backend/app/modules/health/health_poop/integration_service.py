"""The operations other modules may call on health poop records.

The writes stage; the caller owns the unit of work and commits.
"""

from sqlalchemy.orm import Session

import modules.health.health_poop.crud as health_poop_crud
import modules.health.health_poop.schema as health_poop_schema
import modules.health.health_poop.service as health_poop_service
import modules.users.users_profile.contracts as users_profile_contracts


def list_health_poop_by_date(user_id: int, date: str, db: Session) -> list[health_poop_schema.HealthPoopRead]:
    """Return a user's poop records for a calendar date in their own timezone.

    Args:
        user_id: The records' owner.
        date: The calendar date.
        db: Database session.

    Returns:
        The records of that date, newest first.
    """
    return health_poop_service.list_health_poop_by_date(user_id, date, db)


def profile_section() -> users_profile_contracts.ProfileRecordsSection:
    """Return the poop records' section of a profile export and import.

    Returns:
        The section, which exports a user's poop records and stages the archived ones.
    """
    return users_profile_contracts.ProfileRecordsSection(
        key="health_poop",
        export=health_poop_crud.get_health_poop_by_user_id,
        restore=health_poop_service.restore_profile_records,
    )
